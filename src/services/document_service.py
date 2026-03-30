"""
Document service: parse file, optional reformat via LLM, create node via BACKEND_SERVER, trigger embedding.
Supports running as a background job: run_process_document_task(ctx) for task_registry.

Node rows are created by the main backend (POST /nodes), not ORM insert here.
Authorization (Bearer token) is passed in job metadata for those HTTP calls — stored in DB with the job.
"""
import asyncio
import logging
from pathlib import Path
from typing import List, Optional, Any, Dict
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.database import get_silent_db
from src.repositories.file_repository import FileRepository
from src.services.document_parse_service import parse_document, parse_pdf_via_llm_vision
import src.services.llm_router as LLM

logger = logging.getLogger(__name__)


def _node_display_name_from_filename(filename: Optional[str]) -> str:
    """Use filename without final extension (e.g. strip .pdf) for node_name."""
    if not filename or not str(filename).strip():
        return "Untitled"
    base = Path(str(filename).strip()).stem
    return (base if base else "Untitled")[:255]

ReformatOption = str  # "rearrange" | "fill_missing_ai" | "to_bullet_points" | "to_table" | "summarize"

# Job type for document processing (must exist in JobTypes table)
JOB_TYPE_PROCESS_DOCUMENT = "process_document"

DEFAULT_WORKSPACE_RELATION_TYPE = "PART"
BACKEND_REQUEST_TIMEOUT = 120.0


def _backend_api_base() -> str:
    return (settings.backend_server or "").rstrip("/")


def _parse_backend_envelope(data: Any) -> Dict[str, Any]:
    """Expect { status: true, resultData: {...} } from BACKEND_SERVER."""
    if not isinstance(data, dict):
        raise ValueError("Backend response is not a JSON object")
    if not data.get("status"):
        err = data.get("resultData") or data.get("message") or data.get("error") or data
        raise ValueError(f"Backend request failed: {err}")
    inner = data.get("resultData")
    if not isinstance(inner, dict):
        raise ValueError("Backend response missing resultData object")
    return inner


def generate_node_desc_from_content(node_content_md: str, provider: str = "openai", max_input_chars: int = 120000) -> str:
    """LLM-generated short description for node_desc (node_content_md unchanged)."""
    text = (node_content_md or "").strip()
    if not text:
        return ""
    chunk = text[:max_input_chars]
    system_prompt = (
        "Write a concise node description (2–4 sentences) summarizing the document for a knowledge base. "
        "No title line, no markdown headings, no bullet list unless essential. Plain text or light markdown only."
    )
    try:
        out = LLM.simple_chat(chunk, provider=provider, system_prompt=system_prompt)
        return (out or "").strip()[:2000]
    except Exception:
        return (chunk[:500] + "…") if len(chunk) > 500 else chunk


def _http_client(auth_header: str) -> httpx.Client:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header
    return httpx.Client(timeout=BACKEND_REQUEST_TIMEOUT, headers=headers)


def create_node_on_backend(
    node_name: str,
    node_desc: str,
    node_content_md: str,
    auth_header: str,
) -> UUID:
    url = f"{_backend_api_base()}/nodes"
    payload = {
        "node_name": node_name[:255],
        "node_desc": node_desc or "",
        "node_content_md": node_content_md or "",
    }
    with _http_client(auth_header) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        inner = _parse_backend_envelope(r.json())
    raw_id = inner.get("node_id")
    if not raw_id:
        raise ValueError("Backend /nodes response missing resultData.node_id")
    return UUID(str(raw_id))


def create_workspace_relation_on_backend(
    workspace_id: UUID,
    node_id: UUID,
    auth_header: str,
    relation_type_id: str = DEFAULT_WORKSPACE_RELATION_TYPE,
) -> None:
    url = f"{_backend_api_base()}/relations"
    payload = {
        "parent_id": str(workspace_id),
        "child_id": str(node_id),
        "relation_type_id": relation_type_id,
    }
    with _http_client(auth_header) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        try:
            body = r.json()
        except Exception:
            body = None
        if isinstance(body, dict) and body.get("status") is False:
            raise ValueError(f"Backend /relations failed: {body}")
        if isinstance(body, dict) and body.get("status") is True:
            try:
                _parse_backend_envelope(body)
            except ValueError:
                pass


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
    workspace_id_raw = meta.get("workspace_id")
    workspace_id: Optional[UUID] = None
    if workspace_id_raw:
        workspace_id = UUID(workspace_id_raw) if isinstance(workspace_id_raw, str) else workspace_id_raw
    authorization = (meta.get("authorization") or meta.get("Authorization") or "").strip() or None

    if not file_id:
        raise ValueError("metadata.file_id is required")
    if create_node:
        if workspace_id is None:
            raise ValueError("metadata.workspace_id is required when create_node is true")
        if not authorization:
            raise ValueError("metadata.authorization is required when create_node is true")

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
            workspace_id=workspace_id,
            authorization=authorization,
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
        "Clean up OCR artifacts, fix obvious errors, and return only the cleaned, structured content. "
        "If the input is or should remain Markdown (headings #, lists, links, fenced code, tables), "
        "output valid Markdown and preserve those constructs; do not strip markdown solely to plain text. "
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
        system_prompt = (
            "Translate the following content to English. Preserve structure (headings, lists, paragraphs). "
            "If the content is Markdown, keep valid Markdown (headings, lists, links, code fences, tables). "
            "Return only the translated text. No preamble or commentary."
        )
    elif translate_to == "th":
        system_prompt = (
            "Translate the following content to Thai. Preserve structure (headings, lists, paragraphs). "
            "If the content is Markdown, keep valid Markdown (headings, lists, links, code fences, tables). "
            "Return only the translated text. No preamble or commentary."
        )
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
    workspace_id: Optional[UUID] = None,
    authorization: Optional[str] = None,
) -> dict:
    """
    Load file, parse, optionally reformat/translate, create node via BACKEND_SERVER, trigger embedding job.
    translate_to: 'en' = English, 'th' = Thai, None = no translation.
    When create_node is true, workspace_id and authorization (Bearer) are required for /nodes and /relations.
    Returns dict with node_id, node_name, job_id (if create_node).
    """
    repo_file = FileRepository(db)
    file_entity = repo_file.find_one_by_id(file_id)
    if not file_entity:
        raise ValueError(f"File {file_id} not found")
    if file_entity.created_by != user_id:
        raise PermissionError("You don't have permission to process this file")

    # Resolve path so it works across different deploy layouts.
    # Example DB value: "uploads/<user_id>/<filename>.pdf"
    raw_path = Path(file_entity.file_path or "")
    candidates: list[Path] = []
    if raw_path:
        candidates.append(raw_path)
        if not raw_path.is_absolute():
            # 1) As-is relative to current working directory
            candidates.append(Path.cwd() / raw_path)

            # 2) Relative to UPLOAD_DIR (preserve subfolders)
            upload_dir = Path(settings.upload_dir)
            if raw_path.parts and raw_path.parts[0] == upload_dir.name:
                # raw_path already starts with "uploads/..." (common DB format)
                candidates.append(Path.cwd() / raw_path)
                candidates.append(Path("app") / raw_path)  # fallback: "app/uploads/..."
            else:
                # raw_path is something like "<user_id>/<filename>" (not starting with uploads)
                candidates.append(upload_dir / raw_path)
                candidates.append(Path.cwd() / upload_dir / raw_path)
                candidates.append(Path("app") / upload_dir / raw_path)

            # 3) Explicit fallback requested by user: app/<raw_path>
            candidates.append(Path("app") / raw_path)

    resolved: Path | None = None
    for p in candidates:
        try:
            if p.exists():
                resolved = p.resolve()
                break
        except OSError:
            continue

    if not resolved:
        raise ValueError(
            f"File not found on disk: {file_entity.file_path}"
        )

    resolved_file_path = str(resolved)

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
    # null / [] => skip reformat; persist extraction (+ optional extract/translate) as node_content_md
    reformat_opts: List[str] = list(reformat_options) if reformat_options else []
    if reformat_opts:
        text = apply_reformat(text, reformat_opts, provider=llm_provider)
    if translate_to in ("en", "th"):
        text = apply_translate(text, translate_to, provider=llm_provider)

    node_name = _node_display_name_from_filename(file_entity.file_name)
    job_id = None
    node_id: Optional[UUID] = None

    if create_node:
        if workspace_id is None or not authorization or not authorization.strip():
            raise ValueError("workspace_id and authorization are required when create_node is true")
        node_desc = generate_node_desc_from_content(text, provider=llm_provider)
        node_id = create_node_on_backend(
            node_name=node_name,
            node_desc=node_desc,
            node_content_md=text,
            auth_header=authorization.strip(),
        )
        create_workspace_relation_on_backend(
            workspace_id=workspace_id,
            node_id=node_id,
            auth_header=authorization.strip(),
        )

    return {
        "file_id": file_id,
        "node_id": node_id,
        "node_name": node_name if create_node else None,
        "job_id": job_id,
    }
