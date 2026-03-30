"""
Service for LLM-powered relation suggestion between two nodes.
Loads allowed relation_type_id from RelationTypes, asks LLM to pick exactly one.
"""
import json
import re
import logging
from typing import Dict, Set
from uuid import UUID
from sqlalchemy.orm import Session

from src.repositories.node_repository import NodeRepository
from src.repositories.base_repository import BaseRepository
from src.database.models import Relationtypes
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


def suggest_relation(
    db: Session,
    node_a_id: UUID,
    node_b_id: UUID,
    provider: str = "openai",
) -> Dict[str, str]:
    """
    Load two nodes and allowed types from RelationTypes; ask LLM to choose exactly one
    relation_type_id from that set. Returns { "relation_type_id", "explanation" }.
    """
    allowed_ids = _load_allowed_relation_type_ids(db)
    allowed_list = sorted(allowed_ids)
    allowed_json = json.dumps(allowed_list)

    node_repo = NodeRepository(db)
    node_a = node_repo.find_one_by_id(node_a_id)
    node_b = node_repo.find_one_by_id(node_b_id)

    if not node_a:
        raise ValueError(f"Node {node_a_id} not found")
    if not node_b:
        raise ValueError(f"Node {node_b_id} not found")

    content_a = (node_a.node_content_md or "").strip() or "(No content)"
    content_b = (node_b.node_content_md or "").strip() or "(No content)"
    if len(content_a) > MAX_CONTENT_LEN:
        content_a = content_a[:MAX_CONTENT_LEN] + "..."
    if len(content_b) > MAX_CONTENT_LEN:
        content_b = content_b[:MAX_CONTENT_LEN] + "..."

    system_prompt = (
        "You classify how Content A relates to Content B using exactly one relation type from the database. "
        f"The only valid values for relation_type_id are exactly these strings (JSON array): {allowed_json}. "
        'Return a single JSON object with exactly two keys: "relation_type_id" (must be one of those strings '
        'exactly, character for character) and "explanation" (one short sentence in the same language as the content). '
        "Return only that JSON object, no markdown, no code fence, no other text."
    )
    user_message = (
        f"Content A:\n{content_a}\n\n---\n\nContent B:\n{content_b}\n\n"
        "Choose the single best relation_type_id from the allowed list for how A relates to B. "
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
