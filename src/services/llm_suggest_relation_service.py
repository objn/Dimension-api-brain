"""
Service for LLM-powered relation suggestion between two nodes.
Reads node content, asks LLM for 3-5 relation suggestions, returns structured list.
"""
import json
import re
import logging
from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session

from src.repositories.node_repository import NodeRepository
from src.database.models import Nodes
import src.services.llm_router as llm_router

logger = logging.getLogger(__name__)

# Max characters per node content to send to LLM (avoid token limits)
MAX_CONTENT_LEN = 4000


def suggest_relations(
    db: Session,
    node_a_id: UUID,
    node_b_id: UUID,
    provider: str = "openai",
) -> List[Dict[str, str]]:
    """
    Load content of two nodes, ask LLM to suggest 3-5 relations between them,
    return list of { "relation_type_id": str, "explanation": str }.
    """
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
        "You are an assistant that suggests possible relations between two pieces of content. "
        "Return a JSON array of 3 to 5 objects. Each object must have exactly two keys: "
        '"relation_type_id" (a short identifier like RELATED, CONTAINS, DEPENDS_ON, REFERENCES, SUPPORTS) '
        'and "explanation" (one short sentence in the same language as the content). '
        "Return only the JSON array, no markdown, no code fence, no other text."
    )
    user_message = (
        f"Content A:\n{content_a}\n\n---\n\nContent B:\n{content_b}\n\n"
        "Suggest 3 to 5 possible relations between Content A and Content B. "
        "Return only a JSON array of objects with relation_type_id and explanation."
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

    suggestions = _parse_suggestions(raw)
    return suggestions[:5]


def _parse_suggestions(raw: str) -> List[Dict[str, str]]:
    """Parse LLM response into list of { relation_type_id, explanation }. Returns 1-5 items."""
    text = raw.strip()
    # Remove markdown code block if present
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Fallback: try to find a JSON array in the text
        match = re.search(r"\[\s*\{[\s\S]*\}\s*\]", text)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                data = []
        else:
            data = []

    if not isinstance(data, list):
        return []

    result: List[Dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        rt = item.get("relation_type_id")
        ex = item.get("explanation") or ""
        if isinstance(rt, str) and rt.strip():
            result.append({
                "relation_type_id": rt.strip(),
                "explanation": str(ex).strip() if ex else "No explanation",
            })
        if len(result) >= 5:
            break
    return result if result else [
        {"relation_type_id": "RELATED", "explanation": "The two contents are related (LLM did not return structured suggestions)."}
    ]
