"""
Semantic Search Service.
RAG retrieval: embed query, similarity search over Nodevector, return top-k chunks.
Supports cross-lingual search: translate query to other language(s) and merge results.
"""
import logging
from typing import List, Optional, Dict, Tuple
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select

from src.database.models import Nodevector
from src.config.settings import settings
from src.dto.rag_dto import (
    RAGSearchResult,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_SEARCH_LIMIT,
)
from .embedding import EmbeddingService, embedding_service

logger = logging.getLogger(__name__)


def _has_thai_char(text: str) -> bool:
    """True if text contains at least one Thai Unicode character."""
    if not text:
        return False
    for c in text:
        if "\u0E00" <= c <= "\u0E7F":
            return True
    return False


class SemanticSearchService:
    """
    Service for semantic search over embedded node chunks.
    Uses cosine distance on Nodevector.embedding; returns chunks with similarity score.
    """

    def __init__(self, embedder: Optional[EmbeddingService] = None):
        self.embedder = embedder or embedding_service

    def _search_with_embedding(
        self,
        db: Session,
        query_embedding: List[float],
        limit: int,
        min_similarity: Optional[float],
        scope_node_ids: Optional[List[UUID]],
    ) -> List[RAGSearchResult]:
        """Run one similarity search with a precomputed query embedding. Used internally."""
        if scope_node_ids is not None and len(scope_node_ids) == 0:
            scope_node_ids = None
        distance_col = Nodevector.embedding.cosine_distance(query_embedding)
        q = (
            select(
                Nodevector.node_id,
                Nodevector.node_vector_chunk_id,
                Nodevector.node_content_md_chunk,
                Nodevector.node_vector_chunk_order,
                distance_col.label("cosine_dist"),
            )
            .where(Nodevector.deleted_at.is_(None))
            .order_by(distance_col.asc())
            .limit(limit)
        )
        if scope_node_ids:
            q = q.where(Nodevector.node_id.in_(scope_node_ids))
        rows = db.execute(q).all()
        results: List[RAGSearchResult] = []
        for r in rows:
            dist = float(r.cosine_dist) if r.cosine_dist is not None else 0.0
            similarity = 1.0 - dist
            if min_similarity is not None and similarity < min_similarity:
                continue
            results.append(
                RAGSearchResult(
                    node_id=r.node_id,
                    chunk_id=r.node_vector_chunk_id,
                    node_content_md_chunk=r.node_content_md_chunk or "",
                    similarity=round(similarity, 4),
                    node_vector_chunk_order=r.node_vector_chunk_order,
                )
            )
        return results

    def search(
        self,
        db: Session,
        query_text: str,
        limit: int = DEFAULT_SEARCH_LIMIT,
        min_similarity: Optional[float] = DEFAULT_SIMILARITY_THRESHOLD,
        scope_node_ids: Optional[List[UUID]] = None,
    ) -> List[RAGSearchResult]:
        """
        Run semantic search: embed query, find nearest chunks by cosine distance.
        When cross-lingual is enabled, also translates query to the other language (en/th)
        and merges results so content with similar meaning in another language can be found.

        Args:
            db: Database session
            query_text: Natural language query
            limit: Max number of chunks to return
            min_similarity: Minimum similarity (1 - cosine_distance); filter out lower
            scope_node_ids: If set, restrict search to these node IDs

        Returns:
            List of RAGSearchResult ordered by similarity (highest first)
        """
        if not query_text or not query_text.strip():
            return []

        query_stripped = query_text.strip()
        # Build query variants: original + optional translated (for cross-lingual)
        query_variants: List[str] = [query_stripped]
        if settings.rag_cross_lingual_enabled:
            from src.services.document_service import translate_query_for_rag
            # Translate to the other language so we can match content in that language
            target = "en" if _has_thai_char(query_stripped) else "th"
            translated = translate_query_for_rag(
                query_stripped,
                translate_to=target,
                provider=settings.rag_query_translate_llm_provider,
            )
            if translated and translated != query_stripped:
                query_variants.append(translated)
            else:
                if translated is None:
                    logger.debug("Cross-lingual: query translation returned nothing, using single query")
                else:
                    logger.debug("Cross-lingual: translated same as original, using single query")

        if scope_node_ids is not None and len(scope_node_ids) == 0:
            scope_node_ids = None

        # Fetch more per variant so after merge we have enough for top `limit`
        per_query_limit = limit * 2 if len(query_variants) > 1 else limit * 3
        merged: Dict[Tuple[UUID, UUID], RAGSearchResult] = {}
        for qv in query_variants:
            query_embedding = self.embedder.embed_single(qv)
            if not query_embedding:
                continue
            chunk_results = self._search_with_embedding(
                db, query_embedding, per_query_limit, min_similarity, scope_node_ids
            )
            for r in chunk_results:
                key = (r.node_id, r.chunk_id)
                if key not in merged or merged[key].similarity < r.similarity:
                    merged[key] = r

        results = sorted(merged.values(), key=lambda x: -x.similarity)
        if min_similarity is not None:
            results = [r for r in results if r.similarity >= min_similarity]
        return results[:limit]


semantic_search_service = SemanticSearchService()
