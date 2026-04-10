"""
Semantic search over FileVector (conversation-scoped attached documents).
"""
import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import Filevector
from src.config.settings import settings
from src.dto.rag_dto import (
    FileRAGSearchResult,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_SEARCH_LIMIT,
)
from .embedding import EmbeddingService, embedding_service

logger = logging.getLogger(__name__)


def _has_thai_char(text: str) -> bool:
    for c in text or "":
        if "\u0E00" <= c <= "\u0E7F":
            return True
    return False


class FileSemanticSearchService:
    """Similarity search on FileVector.embedding, scoped by conversation_id (and optional file_ids)."""

    def __init__(self, embedder: Optional[EmbeddingService] = None):
        self.embedder = embedder or embedding_service

    def _search_with_embedding(
        self,
        db: Session,
        query_embedding: List[float],
        limit: int,
        min_similarity: Optional[float],
        conversation_id: UUID,
        scope_file_ids: Optional[List[UUID]],
    ) -> List[FileRAGSearchResult]:
        if scope_file_ids is not None and len(scope_file_ids) == 0:
            return []
        distance_col = Filevector.embedding.cosine_distance(query_embedding)
        q = (
            select(
                Filevector.conversation_id,
                Filevector.file_id,
                Filevector.file_vector_chunk_id,
                Filevector.file_content_text_chunk,
                Filevector.file_vector_chunk_order,
                distance_col.label("cosine_dist"),
            )
            .where(Filevector.deleted_at.is_(None))
            .where(Filevector.conversation_id == conversation_id)
            .order_by(distance_col.asc())
            .limit(limit)
        )
        if scope_file_ids:
            q = q.where(Filevector.file_id.in_(scope_file_ids))
        rows = db.execute(q).all()
        out: List[FileRAGSearchResult] = []
        for r in rows:
            dist = float(r.cosine_dist) if r.cosine_dist is not None else 0.0
            similarity = 1.0 - dist
            if min_similarity is not None and similarity < min_similarity:
                continue
            out.append(
                FileRAGSearchResult(
                    conversation_id=r.conversation_id,
                    file_id=r.file_id,
                    chunk_id=r.file_vector_chunk_id,
                    file_content_text_chunk=r.file_content_text_chunk or "",
                    similarity=round(similarity, 4),
                    file_vector_chunk_order=r.file_vector_chunk_order,
                )
            )
        return out

    def search(
        self,
        db: Session,
        query_text: str,
        conversation_id: UUID,
        limit: int = DEFAULT_SEARCH_LIMIT,
        min_similarity: Optional[float] = DEFAULT_SIMILARITY_THRESHOLD,
        scope_file_ids: Optional[List[UUID]] = None,
    ) -> List[FileRAGSearchResult]:
        if not query_text or not query_text.strip():
            return []

        query_stripped = query_text.strip()
        if scope_file_ids is not None and len(scope_file_ids) == 0:
            return []

        query_variants: List[str] = [query_stripped]
        if settings.rag_cross_lingual_enabled:
            from src.services.document_service import translate_query_for_rag

            target = "en" if _has_thai_char(query_stripped) else "th"
            translated = translate_query_for_rag(
                query_stripped,
                translate_to=target,
                provider=settings.rag_query_translate_llm_provider,
            )
            if translated and translated != query_stripped:
                query_variants.append(translated)

        per_query_limit = limit * 2 if len(query_variants) > 1 else limit * 3
        merged: dict[tuple[UUID, UUID], FileRAGSearchResult] = {}
        for qv in query_variants:
            query_embedding = self.embedder.embed_single(qv)
            if not query_embedding:
                continue
            chunk_results = self._search_with_embedding(
                db,
                query_embedding,
                per_query_limit,
                min_similarity,
                conversation_id,
                scope_file_ids,
            )
            for r in chunk_results:
                key = (r.file_id, r.chunk_id)
                if key not in merged or merged[key].similarity < r.similarity:
                    merged[key] = r

        results = sorted(merged.values(), key=lambda x: -x.similarity)
        if min_similarity is not None:
            results = [r for r in results if r.similarity >= min_similarity]
        return results[:limit]


file_semantic_search_service = FileSemanticSearchService()
