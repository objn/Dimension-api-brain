"""
Service for LLM-powered relation suggestion between two entities (node, workspace, file).
Loads allowed relation_type_id from RelationTypes, asks LLM to pick exactly one.
"""
import json
import re
import logging
from typing import Dict, Set
from uuid import UUID
from sqlalchemy.orm import Session

from src.dto.llm_dto import RelationEntityType
from src.repositories.node_repository import NodeRepository
from src.repositories.file_repository import FileRepository
from src.repositories.base_repository import BaseRepository
from src.database.models import Relationtypes, Workspaces
import src.services.llm_router as llm_router

logger = logging.getLogger(__name__)

MAX_CONTENT_LEN = 4000


def _load_allowed_relation_type_ids(db: Session) -> Set[str]:
    repo = BaseRepository(Relationtypes, db)
    rows = repo.find_all()
    allowed = {r.relation_type_id for r in rows if r.relation_type_id}
    if not allowed:
        raise ValueError("No relation types defined in the database (RelationTypes is empty).")
    return allowed


def _resolve_side_text(
    db: Session,
    entity_id: UUID,
    entity_type: RelationEntityType,
    user_id: UUID,
) -> str:
    """
    Load text for one side of suggest-relation. Enforces created_by == user_id.
    Raises ValueError if not found; PermissionError if not owner.
    """
    if entity_type == RelationEntityType.NODE:
        node_repo = NodeRepository(db)
        row = node_repo.find_one_by_id(entity_id)
        if not row:
            raise ValueError(f"Node {entity_id} not found")
        if row.created_by != user_id:
            raise PermissionError("You don't have permission to use this node for relation suggestion")
        parts = [
            f"Title: {row.node_name or 'Untitled'}",
            f"Description: {(row.node_desc or '').strip() or '(No description)'}",
            f"Content:\n{(row.node_content_md or '').strip() or '(No content)'}",
        ]
        text = "\n\n".join(parts)
    elif entity_type == RelationEntityType.WORKSPACE:
        row = db.query(Workspaces).filter(Workspaces.workspace_id == entity_id).first()
        if not row:
            raise ValueError(f"Workspace {entity_id} not found")
        if row.created_by != user_id:
            raise PermissionError("You don't have permission to use this workspace for relation suggestion")
        parts = [
            f"Workspace name: {row.workspace_name or 'Untitled'}",
            f"Description: {(row.workspace_desc or '').strip() or '(No description)'}",
        ]
        text = "\n\n".join(parts)
    else:
        file_repo = FileRepository(db)
        row = file_repo.find_one_by_id(entity_id)
        if not row:
            raise ValueError(f"File {entity_id} not found")
        if row.created_by != user_id:
            raise PermissionError("You don't have permission to use this file for relation suggestion")
        size = row.file_size if row.file_size is not None else "unknown"
        text = (
            f"File name: {row.file_name or '(unnamed)'}\n"
            f"MIME type: {row.mime_type or 'unknown'}\n"
            f"Size bytes: {size}\n\n"
            "Note: Full document text is not loaded in this endpoint; only file metadata is available."
        )

    if len(text) > MAX_CONTENT_LEN:
        text = text[:MAX_CONTENT_LEN] + "..."
    return text


def suggest_relation(
    db: Session,
    parent_id: UUID,
    child_id: UUID,
    type_of_parent: RelationEntityType,
    type_of_child: RelationEntityType,
    user_id: UUID,
    provider: str = "openai",
) -> Dict[str, str]:
    """
    Resolve parent/child content by entity type; ask LLM for one relation_type_id from RelationTypes.
    Semantics: choose how the parent entity relates to the child entity (parent_id -> child_id).
    Returns { "relation_type_id", "explanation" }.
    """
    allowed_ids = _load_allowed_relation_type_ids(db)
    allowed_list = sorted(allowed_ids)
    allowed_json = json.dumps(allowed_list)

    content_parent = _resolve_side_text(db, parent_id, type_of_parent, user_id)
    content_child = _resolve_side_text(db, child_id, type_of_child, user_id)

    system_prompt = (
        "You classify how the PARENT entity relates to the CHILD entity using exactly one relation type "
        "from the database. The relation is directed: parent_id is the parent side and child_id is the child side "
        "(as in a graph edge parent -> child). "
        f"The only valid values for relation_type_id are exactly these strings (JSON array): {allowed_json}. "
        'Return a single JSON object with exactly two keys: "relation_type_id" (must be one of those strings '
        'exactly, character for character) and "explanation" (one short sentence in the same language as the content). '
        "Return only that JSON object, no markdown, no code fence, no other text."
    )
    user_message = (
        f"Parent ({type_of_parent.value}) id {parent_id}:\n{content_parent}\n\n---\n\n"
        f"Child ({type_of_child.value}) id {child_id}:\n{content_child}\n\n"
        "Choose the single best relation_type_id from the allowed list for how the PARENT relates to the CHILD. "
        "Return only one JSON object with relation_type_id and explanation."
    )

    try:
        raw = llm_router.simple_chat(
            message=user_message,
            provider=provider,
            system_prompt=system_prompt,
        )
    except Exception as e:
        logger.warning("LLM suggest_relation failed: %s", e)
        raise ValueError(f"LLM request failed: {e}") from e

    return _parse_and_validate_suggestion(raw, allowed_ids)


def _try_parse_first_json_object(text: str):
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _parse_and_validate_suggestion(raw: str, allowed_ids: Set[str]) -> Dict[str, str]:
    text = raw.strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()

    data = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[\s*\{[\s\S]*?\}\s*\]", text)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                data = None
        if data is None:
            data = _try_parse_first_json_object(text)

    item = None
    if isinstance(data, dict):
        item = data
    elif isinstance(data, list):
        if len(data) != 1:
            raise ValueError(
                "LLM must return a single JSON object or a JSON array of exactly one object."
            )
        if isinstance(data[0], dict):
            item = data[0]

    if not item:
        raise ValueError("Could not parse a single relation suggestion from LLM response.")

    rt = item.get("relation_type_id")
    ex = item.get("explanation") or ""
    if not isinstance(rt, str) or not rt.strip():
        raise ValueError("LLM response missing valid relation_type_id string.")
    rt_clean = rt.strip()
    if rt_clean not in allowed_ids:
        raise ValueError(
            f"LLM returned relation_type_id not in RelationTypes: {rt_clean!r}"
        )
    explanation = str(ex).strip() if ex else "No explanation"
    return {"relation_type_id": rt_clean, "explanation": explanation}
