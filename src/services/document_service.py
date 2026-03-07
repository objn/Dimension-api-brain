"""
Document service: parse file, optional reformat via LLM, create node, trigger embedding.
Supports running as a background job: run_process_document_task(ctx) for task_registry.
"""
import asyncio
from pathlib import Path
from typing import List, Optional, Any, Dict
from uuid import UUID, uuid4
from datetime import datetime

from sqlalchemy.orm import Session

from src.config.settings import settings
from src.database.models import Files, Nodes
from src.database import get_silent_db
from src.repositories.file_repository import FileRepository
from src.repositories.node_repository import NodeRepository
from src.services.document_parse_service import parse_document, parse_pdf_via_llm_vision
import src.services.llm_router as LLM

ReformatOption = str  # "rearrange" | "fill_missing_ai" | "to_bullet_points" | "to_table" | "summarize"

# Job type for document processing (must exist in JobTypes table)
JOB_TYPE_PROCESS_DOCUMENT = "process_document"


def run_process_document_task(ctx: "JobContext") -> Dict[str, Any]:
    """
    Task function for process_document job. Called by JobService when daemon activates the job.
    Reads file_id, user_id, options from ctx.metadata; runs process_document; optionally
    registers embedding job. Returns result dict (file_id, node_id, node_name, embedding_job_id).
    """
    from src.services.rag import node_embedding_service

    meta = ctx.metadata or {}
    file_id = UUID(meta["file_id"]) if isinstance(meta.get("file_id"), str) else meta.get("file_id")
    user_id = ctx.user_id
    reformat_options = meta.get("reformat_options") or []
    llm_provider = meta.get("llm_provider") or "openai"
    create_node = meta.get("create_node", True)
    use_llm_extract = meta.get("use_llm_extract", False)
    max_pages_per_call = int(meta.get("max_pages_per_call") or 5)
    translate_to = meta.get("translate_to")  # "en" | "th" | None

    if not file_id:
        raise ValueError("metadata.file_id is required")

    db_gen = get_silent_db()
    db = next(db_gen)
    try:
        result = process_document(
            db=db,
            file_id=file_id,
            user_id=user_id,
            reformat_options=reformat_options,
            llm_provider=llm_provider,
            create_node=create_node,
            use_llm_extract=use_llm_extract,
            max_pages_per_call=max_pages_per_call,
            translate_to=translate_to,
        )
        embedding_job_id = None
        if create_node and result.get("node_id"):
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                embedding_job_id = loop.run_until_complete(
                    node_embedding_service.embed_node(
                        node_id=result["node_id"],
                        user_id=user_id,
                        db=db,
                        force_reembed=False,
                    )
                )
                loop.close()
            except Exception as e:
                result["embedding_job_error"] = str(e)
        result["embedding_job_id"] = str(embedding_job_id) if embedding_job_id else None
        # Return JSON-serializable dict for job metadata (GET /jobs/{job_id})
        return {
            "file_id": str(result.get("file_id")),
            "node_id": str(result["node_id"]) if result.get("node_id") else None,
            "node_name": result.get("node_name") or "",
            "embedding_job_id": result.get("embedding_job_id"),
            "embedding_job_error": result.get("embedding_job_error"),
        }
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


def apply_reformat(text: str, options: List[str], provider: str = "openai") -> str:
    """Apply selected reformat options to extracted text using LLM. Returns transformed text."""
    if not text or not text.strip() or not options:
        return text
    instructions = []
    if "rearrange" in options:
        instructions.append("reorder sections for clarity and logical flow")
    if "fill_missing_ai" in options:
        instructions.append("fill in obvious gaps or incomplete sentences using inference")
    if "to_bullet_points" in options:
        instructions.append("convert paragraphs into bullet points where appropriate")
    if "to_table" in options:
        instructions.append("detect tabular content and format as markdown tables")
    if "summarize" in options:
        instructions.append("add a short summary at the top (2-4 sentences)")
    if not instructions:
        return text
    system_prompt = (
        "You are a document editor. Apply these transformations to the content:\n- "
        + "\n- ".join(instructions)
        + "\n\nReturn ONLY the transformed content in markdown. No preamble or commentary."
    )
    try:
        return LLM.simple_chat(text[:120000], provider=provider, system_prompt=system_prompt)
    except Exception:
        return text


def apply_llm_extract(text: str, provider: str = "openai") -> str:
    """Use LLM to extract, clean, and structure content from parsed text (e.g. post-OCR)."""
    if not text or not text.strip():
        return text
    system_prompt = (
        "Extract and structure the main content from the following text. "
        "Clean up OCR artifacts, fix obvious errors, and return only the cleaned, structured content in markdown. "
        "No preamble or commentary."
    )
    try:
        return LLM.simple_chat(text[:120000], provider=provider, system_prompt=system_prompt)
    except Exception:
        return text


def apply_translate(text: str, translate_to: str, provider: str = "openai") -> str:
    """Translate content to the target language via LLM. translate_to: 'en' = English, 'th' = Thai."""
    if not text or not text.strip() or not translate_to:
        return text
    if translate_to == "en":
        system_prompt = "Translate the following content to English. Preserve structure (headings, lists, paragraphs). Return only the translated text in markdown. No preamble or commentary."
    elif translate_to == "th":
        system_prompt = "Translate the following content to Thai. Preserve structure (headings, lists, paragraphs). Return only the translated text in markdown. No preamble or commentary."
    else:
        return text
    try:
        return LLM.simple_chat(text[:120000], provider=provider, system_prompt=system_prompt)
    except Exception:
        return text


def translate_query_for_rag(query: str, translate_to: str, provider: str = "openai", max_chars: int = 2000) -> Optional[str]:
    """
    Translate a short query for cross-lingual RAG search.
    translate_to: 'en' or 'th'. Returns translated string or None if empty/failed.
    """
    if not query or not query.strip():
        return None
    text = query.strip()[:max_chars]
    try:
        out = apply_translate(text, translate_to, provider=provider)
        return out.strip() if out and out.strip() else None
    except Exception:
        return None


def process_document(
    db: Session,
    file_id: UUID,
    user_id: UUID,
    reformat_options: Optional[List[ReformatOption]] = None,
    llm_provider: str = "openai",
    create_node: bool = True,
    use_llm_extract: bool = False,
    max_pages_per_call: int = 5,
    translate_to: Optional[str] = None,
) -> dict:
    """
    Load file, parse, optionally reformat/translate, create node, trigger embedding job.
    translate_to: 'en' = English, 'th' = Thai, None = no translation.
    Returns dict with node_id, node_name, job_id (if create_node).
    """
    repo_file = FileRepository(db)
    file_entity = repo_file.find_one_by_id(file_id)
    if not file_entity:
        raise ValueError(f"File {file_id} not found")
    if file_entity.created_by != user_id:
        raise PermissionError("You don't have permission to process this file")

    # Resolve path so it works whether DB has relative or absolute path (e.g. uploads/xxx.pdf vs C:\...\uploads\xxx.pdf)
    raw_path = Path(file_entity.file_path or "")
    if not raw_path.is_absolute():
        raw_path = (Path(settings.upload_dir) / raw_path.name).resolve()
    if not raw_path.exists():
        raise ValueError(f"File not found on disk: {file_entity.file_path}")
    resolved_file_path = str(raw_path)

    is_pdf = (file_entity.mime_type or "").lower().strip().split(";")[0] == "application/pdf" or (
        (file_entity.file_path or "").lower().endswith(".pdf")
    )

    text = ""
    used_vision_fallback = False
    try:
        text = parse_document(
            resolved_file_path,
            mime_type=file_entity.mime_type,
            filename=file_entity.file_name,
        )
    except ValueError as e:
        if is_pdf and "Could not extract" in str(e):
            text = parse_pdf_via_llm_vision(
                resolved_file_path,
                provider=llm_provider,
                max_pages_per_call=max_pages_per_call,
                timeout_per_batch=120.0,
            )
            used_vision_fallback = True
        else:
            raise
    if not text or len(text.strip()) < 100:
        if is_pdf and not used_vision_fallback:
            text = parse_pdf_via_llm_vision(
                resolved_file_path,
                provider=llm_provider,
                max_pages_per_call=max_pages_per_call,
                timeout_per_batch=120.0,
            )
            used_vision_fallback = True
    if not text or not text.strip():
        raise ValueError("Could not extract any text from the document.")

    if use_llm_extract and not used_vision_fallback:
        text = apply_llm_extract(text, provider=llm_provider)
    if reformat_options:
        text = apply_reformat(text, reformat_options, provider=llm_provider)
    if translate_to in ("en", "th"):
        text = apply_translate(text, translate_to, provider=llm_provider)

    node_name = (file_entity.file_name or "Untitled")[:255]
    summary = None
    if reformat_options and "summarize" in reformat_options and len(text) > 500:
        summary = text[:500].strip()  # Use first portion as node_desc placeholder

    node_repo = NodeRepository(db)
    now = datetime.utcnow()
    node_id = uuid4()
    node = Nodes(
        node_id=node_id,
        node_name=node_name,
        node_desc=summary,
        node_content_md=text,
        node_location_x=None,
        node_location_y=None,
        node_location_z=None,
        created_at=now,
        created_by=user_id,
        updated_at=now,
        updated_by=user_id,
    )
    node_repo.create(node)

    job_id = None
    if create_node:
        # Caller (controller) will await node_embedding_service.embed_node() and pass job_id
        pass

    return {
        "file_id": file_id,
        "node_id": node_id,
        "node_name": node_name,
        "job_id": job_id,
    }
