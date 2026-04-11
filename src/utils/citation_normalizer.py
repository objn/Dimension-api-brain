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


def _first_present(d: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if k in d:
            return d.get(k)
    return None


def _normalize_file_only_citation(item: Dict[str, Any], source_type: str) -> Dict[str, Any]:
    """``file_image`` or ``file``: only Files-table-style fields (no chunk / similarity)."""
    out: Dict[str, Any] = {"source_type": source_type}
    fid = _to_str_uuid(item.get("file_id"))
    if fid:
        out["file_id"] = fid
    if item.get("file_name") is not None:
        out["file_name"] = str(item["file_name"])
    if item.get("mime_type") is not None:
        out["mime_type"] = str(item["mime_type"])
    if item.get("file_size") is not None:
        try:
            out["file_size"] = int(item["file_size"])
        except Exception:
            out["file_size"] = item["file_size"]
    return out


def _expand_chunk_arrays(
    chunk_id_raw: Any,
    chunk_order_raw: Any,
    similarity_score_percent: Optional[float],
    build_row: Any,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if chunk_id_raw is None:
        return rows
    chunk_ids: List[Any] = chunk_id_raw if isinstance(chunk_id_raw, list) else [chunk_id_raw]
    chunk_orders: Optional[List[Any]] = chunk_order_raw if isinstance(chunk_order_raw, list) else None
    for idx, cid in enumerate(chunk_ids):
        chunk_id = _to_str_uuid(cid)
        if not chunk_id:
            continue
        if chunk_orders is not None and idx < len(chunk_orders):
            chunk_order_val = chunk_orders[idx]
        else:
            chunk_order_val = chunk_order_raw
        rows.append(
            build_row(chunk_id, _to_int(chunk_order_val), similarity_score_percent)
        )
    return rows


def normalize_citations_in_metadatas(metadatas: Any) -> Any:
    """
    Normalize metadatas.citations for API response only.

    Polymorphic items (omit unused keys); every item includes ``source_type`` (one of
    ``node``, ``file``, ``file_document``, ``file_image``, ``conversation``):
    - ``node``: RAG chunk or attached node (IDs / names only; no text snippet)
    - ``file_document``: RAG chunk or attached document reference (frontend loads text via FileVector)
    - ``file_image`` / ``file``: attached file metadata (no chunk)
    - ``conversation``: ``conversation_id``, optional ``conversation_topic``
    """
    if not isinstance(metadatas, dict):
        return metadatas

    raw = metadatas.get("citations")
    if not isinstance(raw, list):
        return metadatas

    normalized: List[Dict[str, Any]] = []

    for item in raw:
        if not isinstance(item, dict):
            continue

        source_type = item.get("source_type")

        if source_type == "file_image":
            norm = _normalize_file_only_citation(item, "file_image")
            if norm.get("file_id"):
                normalized.append(norm)
            continue
        if source_type in ("file", "file_unsupported"):
            # file_unsupported: legacy stored citations
            norm = _normalize_file_only_citation(item, "file")
            if norm.get("file_id"):
                normalized.append(norm)
            continue

        if source_type == "conversation":
            conv_id = _to_str_uuid(item.get("conversation_id"))
            if conv_id:
                row_c: Dict[str, Any] = {
                    "source_type": "conversation",
                    "conversation_id": conv_id,
                }
                if item.get("conversation_topic") is not None:
                    row_c["conversation_topic"] = str(item["conversation_topic"])
                normalized.append(row_c)
            continue

        similarity_score_percent = _similarity_to_percent(
            _first_present(item, ["similarity_score", "similarity"])
        )
        chunk_id_raw = _first_present(item, ["chunk_id", "chunk_ids"])
        chunk_order_raw = _first_present(
            item,
            ["chunk_order", "chunk_index", "node_vector_chunk_order", "chunk_orders"],
        )

        node_obj_early = item.get("node") if isinstance(item.get("node"), dict) else {}
        node_id_early = _to_str_uuid(item.get("node_id")) or _to_str_uuid(
            node_obj_early.get("node_id")
        )
        node_name_early = item.get("node_name") or node_obj_early.get("node_name")

        if source_type == "node" and node_id_early and chunk_id_raw is None:
            row_n: Dict[str, Any] = {
                "source_type": "node",
                "node_id": node_id_early,
            }
            if node_name_early is not None:
                row_n["node_name"] = str(node_name_early)
            normalized.append(row_n)
            continue

        fid_early = _to_str_uuid(item.get("file_id"))
        fname_early = item.get("file_name")
        if source_type == "file_document" and fid_early and chunk_id_raw is None:
            row_fd: Dict[str, Any] = {
                "source_type": "file_document",
                "file_id": fid_early,
            }
            if fname_early is not None:
                row_fd["file_name"] = str(fname_early)
            normalized.append(row_fd)
            continue

        if source_type == "file_document" or (
            source_type is None
            and _to_str_uuid(item.get("file_id"))
            and chunk_id_raw is not None
            and not _to_str_uuid(item.get("node_id"))
        ):
            fid = _to_str_uuid(item.get("file_id"))
            fname = item.get("file_name")
            if not fid or chunk_id_raw is None:
                continue

            def _fd_row(
                chunk_id: str, chunk_order: Optional[int], sim_pct: Optional[float]
            ) -> Dict[str, Any]:
                row: Dict[str, Any] = {
                    "source_type": "file_document",
                    "file_id": fid,
                    "chunk_id": chunk_id,
                    "chunk_order": chunk_order,
                    "similarity_score_percent": sim_pct,
                }
                if fname is not None:
                    row["file_name"] = str(fname)
                return row

            normalized.extend(
                _expand_chunk_arrays(chunk_id_raw, chunk_order_raw, similarity_score_percent, _fd_row)
            )
            continue

        # Node RAG (explicit or inferred)
        node_obj = node_obj_early
        node_id = node_id_early
        node_name = node_name_early
        if not node_id or chunk_id_raw is None:
            continue

        def _node_row(
            chunk_id: str, chunk_order: Optional[int], sim_pct: Optional[float]
        ) -> Dict[str, Any]:
            row: Dict[str, Any] = {
                "source_type": "node",
                "node_id": node_id,
                "chunk_id": chunk_id,
                "chunk_order": chunk_order,
                "similarity_score_percent": sim_pct,
            }
            if node_name is not None:
                row["node_name"] = str(node_name)
            return row

        normalized.extend(
            _expand_chunk_arrays(chunk_id_raw, chunk_order_raw, similarity_score_percent, _node_row)
        )

    out = dict(metadatas)
    out["citations"] = normalized
    return out
