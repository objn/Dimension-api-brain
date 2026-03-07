"""
Semantic Search Service.
RAG retrieval: embed query, similarity search over Nodevector, return top-k chunks.
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select

from src.database.models import Nodevector
from src.dto.rag_dto import (
    RAGSearchResult,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_SEARCH_LIMIT,
)
from .embedding import EmbeddingService, embedding_service


class SemanticSearchService:
    """
    Service for semantic search over embedded node chunks.
    Uses cosine distance on Nodevector.embedding; returns chunks with similarity score.
    """

    def __init__(self, embedder: Optional[EmbeddingService] = None):
        self.embedder = embedder or embedding_service

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

        query_embedding = self.embedder.embed_single(query_text.strip())
        if not query_embedding:
            return []

        # Treat empty scope as unscoped (search all nodes)
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
            .limit(limit * 3)
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
            if len(results) >= limit:
                break
        return results


semantic_search_service = SemanticSearchService()
