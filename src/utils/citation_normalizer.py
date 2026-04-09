from __future__ import annotations

from typing import Any, Dict, List, Optional


def _to_str_uuid(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        s = str(value)
        return s if s else None
    except Exception:
        return None


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _similarity_to_percent(similarity: Any) -> Optional[float]:
    sim = _to_float(similarity)
    if sim is None:
        return None
    return round(sim * 100.0, 2)


def normalize_citations_in_metadatas(metadatas: Any) -> Any:
    """
    Normalize metadatas.citations shape for API response only.

    Output citation items:
      { node_id, node_name, chunk_id, chunk_order, similarity_score_percent }
    """
    if not isinstance(metadatas, dict):
        return metadatas

    raw = metadatas.get("citations")
    if not isinstance(raw, list):
        return metadatas

    normalized: List[Dict[str, Any]] = []

    def _first_present(d: Dict[str, Any], keys: List[str]) -> Any:
        """Return the first key that exists in dict (even if value is 0/False)."""
        for k in keys:
            if k in d:
                return d.get(k)
        return None

    for item in raw:
        if not isinstance(item, dict):
            continue

        node_obj = item.get("node") if isinstance(item.get("node"), dict) else {}
        node_id = _to_str_uuid(item.get("node_id")) or _to_str_uuid(node_obj.get("node_id"))
        node_name = item.get("node_name") or node_obj.get("node_name")
        similarity_score_percent = _similarity_to_percent(
            _first_present(item, ["similarity_score", "similarity"])
        )

        # chunk_id may be a string or an array (citation_ref_unique=true case)
        chunk_id_raw = _first_present(item, ["chunk_id", "chunk_ids"])
        chunk_order_raw = _first_present(
            item,
            ["chunk_order", "chunk_index", "node_vector_chunk_order", "chunk_orders"],
        )

        # Only normalize node-vector citations (must have node_id and chunk identifiers)
        if not node_id or chunk_id_raw is None:
            continue

        chunk_ids: List[Any] = chunk_id_raw if isinstance(chunk_id_raw, list) else [chunk_id_raw]
        chunk_orders: Optional[List[Any]] = chunk_order_raw if isinstance(chunk_order_raw, list) else None

        for idx, cid in enumerate(chunk_ids):
            chunk_id = _to_str_uuid(cid)
            if not chunk_id:
                continue

            chunk_order_val: Any = None
            if chunk_orders is not None and idx < len(chunk_orders):
                chunk_order_val = chunk_orders[idx]
            else:
                chunk_order_val = chunk_order_raw

            normalized.append(
                {
                    "node_id": node_id,
                    "node_name": str(node_name) if node_name is not None else None,
                    "chunk_id": chunk_id,
                    "chunk_order": _to_int(chunk_order_val),
                    "similarity_score_percent": similarity_score_percent,
                }
            )

    out = dict(metadatas)
    out["citations"] = normalized
    return out

