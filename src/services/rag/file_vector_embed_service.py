"""
Embed parsed file text into FileVector for a single conversation + file (replace chunks).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from src.database.models import Filevector
from src.repositories.file_vector_repository import FileVectorRepository
from src.services.rag.chunking import chunking_service
from src.services.rag.embedding import embedding_service

logger = logging.getLogger(__name__)


def upsert_file_chunks_for_conversation(
    db: Session,
    conversation_id: UUID,
    file_id: UUID,
    user_id: UUID,
    text: str,
) -> int:
    """
    Soft-delete existing FileVector rows for (conversation_id, file_id), then chunk, embed, insert.
    Returns number of chunk rows inserted.
    """
    repo = FileVectorRepository(db)
    repo.soft_delete_by_conversation_and_file(conversation_id, file_id, user_id)

    stripped = (text or "").strip()
    if not stripped:
        return 0

    chunks = chunking_service.create_content_chunks(stripped)
    chunk_list = [c for c in chunks if c.content and str(c.content).strip()]
    if not chunk_list:
        return 0

    try:
        embeddings: List[List[float]] = embedding_service.embed_batch([c.content for c in chunk_list])
    except Exception as e:
        logger.error("FileVector embed_batch failed for file %s: %s", file_id, e, exc_info=True)
        raise

    if len(embeddings) != len(chunk_list):
        logger.error("FileVector embedding count mismatch for file %s", file_id)
        raise ValueError("Embedding count mismatch")

    now = datetime.utcnow()
    rows: List[Filevector] = []
    for ch, emb in zip(chunk_list, embeddings):
        rows.append(
            Filevector(
                conversation_id=conversation_id,
                file_id=file_id,
                file_vector_chunk_id=uuid4(),
                file_vector_chunk_order=ch.order,
                file_content_text_chunk=ch.content,
                file_content_chunk_hash=ch.content_hash,
                embedding=emb,
                created_at=now,
                created_by=user_id,
                updated_at=now,
                updated_by=user_id,
                deleted_at=None,
            )
        )

    if rows:
        repo.bulk_create(rows)
    return len(rows)
