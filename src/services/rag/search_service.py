"""
Semantic Search Service.
Search across node vectors using pgvector cosine similarity.
"""
from typing import List, Dict, Any, Optional
from uuid import UUID
import logging

from sqlalchemy.orm import Session
from sqlalchemy import text

from src.database.models import Nodes, Nodevector
from .embedding import embedding_service
from .types import DEFAULT_SIMILARITY_THRESHOLD, DEFAULT_SEARCH_LIMIT

logger = logging.getLogger(__name__)


class SearchService:
    """
    Service for semantic search across node vectors.
    
    Uses pgvector's cosine distance operator (<=>).
    Note: Cosine distance = 1 - cosine_similarity
    """
    
    def search(
        self,
        query: str,
        db: Session,
        user_id: Optional[UUID] = None,
        workspace_id: Optional[UUID] = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        include_content: bool = True,
        include_metadata_chunks: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search for similar content across all nodes.
        
        Args:
            query: Search query text
            db: Database session
            user_id: Filter by owner (optional)
            workspace_id: Filter by workspace (optional, for future use)
            limit: Maximum results
            similarity_threshold: Minimum similarity score (0-1)
            include_content: Include chunk content in results
            include_metadata_chunks: Include order=0 chunks
            
        Returns:
            List of search results with similarity scores
        """
        if not query or not query.strip():
            return []
        
        # Create query embedding
        try:
            query_embedding = embedding_service.embed_single(query)
        except Exception as e:
            logger.error(f"Failed to embed query: {e}")
            raise
        
        # Build SQL query using pgvector cosine similarity
        # cosine_distance = 1 - cosine_similarity
        # so similarity = 1 - cosine_distance
        sql = """
            SELECT 
                nv.node_id,
                nv."node_vector_chuck_id" as chunk_id,
                nv."node_vector_chuck_order" as chunk_order,
                nv."node_content_md_chuck" as content,
                nv."node_content_md_chuck_hash" as content_hash,
                n.node_name,
                n.node_desc,
                (1 - (nv.embedding <=> :query_embedding::vector)) as similarity
            FROM "NodeVector" nv
            JOIN "Nodes" n ON nv.node_id = n.node_id
            WHERE nv.deleted_at IS NULL
        """
        
        params = {
            "query_embedding": str(query_embedding),
            "threshold": similarity_threshold,
            "limit": limit
        }
        
        # Optional filters
        if not include_metadata_chunks:
            sql += ' AND nv."node_vector_chuck_order" > 0'
        
        if user_id:
            sql += " AND n.created_by = :user_id"
            params["user_id"] = str(user_id)
        
        # Similarity filter and ordering
        sql += """
            AND (1 - (nv.embedding <=> :query_embedding::vector)) >= :threshold
            ORDER BY similarity DESC
            LIMIT :limit
        """
        
        try:
            result = db.execute(text(sql), params)
            rows = result.fetchall()
        except Exception as e:
            logger.error(f"Search query failed: {e}")
            raise
        
        # Format results
        results = []
        for row in rows:
            result_item = {
                "node_id": str(row.node_id),
                "node_name": row.node_name,
                "node_desc": row.node_desc,
                "chunk_id": str(row.chunk_id),
                "chunk_order": row.chunk_order,
                "chunk_type": "metadata" if row.chunk_order == 0 else "content",
                "similarity": round(float(row.similarity), 4)
            }
            
            if include_content:
                result_item["content"] = row.content
            
            results.append(result_item)
        
        logger.info(f"Search returned {len(results)} results for query: {query[:50]}...")
        return results
    
    def search_in_node(
        self,
        query: str,
        node_id: UUID,
        db: Session,
        limit: int = 5,
        include_metadata: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search within a specific node's chunks.
        
        Args:
            query: Search query text
            node_id: Node to search in
            db: Database session
            limit: Maximum results
            include_metadata: Include metadata chunk (order=0)
            
        Returns:
            List of matching chunks
        """
        if not query or not query.strip():
            return []
        
        query_embedding = embedding_service.embed_single(query)
        
        sql = """
            SELECT 
                "node_vector_chuck_id" as chunk_id,
                "node_vector_chuck_order" as chunk_order,
                "node_content_md_chuck" as content,
                (1 - (embedding <=> :query_embedding::vector)) as similarity
            FROM "NodeVector"
            WHERE node_id = :node_id
            AND deleted_at IS NULL
        """
        
        params = {
            "query_embedding": str(query_embedding),
            "node_id": str(node_id),
            "limit": limit
        }
        
        if not include_metadata:
            sql += ' AND "node_vector_chuck_order" > 0'
        
        sql += """
            ORDER BY similarity DESC
            LIMIT :limit
        """
        
        result = db.execute(text(sql), params)
        
        return [
            {
                "chunk_id": str(row.chunk_id),
                "chunk_order": row.chunk_order,
                "chunk_type": "metadata" if row.chunk_order == 0 else "content",
                "content": row.content,
                "similarity": round(float(row.similarity), 4)
            }
            for row in result.fetchall()
        ]
    
    def find_related_nodes(
        self,
        node_id: UUID,
        db: Session,
        limit: int = 10,
        similarity_threshold: float = 0.5,
        user_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """
        Find nodes related to a given node based on content similarity.
        Uses the metadata chunk (order=0) for comparison.
        
        Args:
            node_id: Source node
            db: Database session
            limit: Maximum results
            similarity_threshold: Minimum similarity
            user_id: Filter by owner
            
        Returns:
            List of related nodes with similarity scores
        """
        # Get metadata chunk (order=0) of source node
        source_vector = db.query(Nodevector).filter(
            Nodevector.node_id == node_id,
            Nodevector.node_vector_chuck_order == 0,
            Nodevector.deleted_at.is_(None)
        ).first()
        
        if not source_vector or not source_vector.embedding:
            logger.warning(f"No metadata chunk found for node {node_id}")
            return []
        
        # Find similar nodes by comparing metadata chunks
        sql = """
            WITH node_similarities AS (
                SELECT DISTINCT ON (n.node_id)
                    n.node_id,
                    n.node_name,
                    n.node_desc,
                    (1 - (nv.embedding <=> :source_embedding::vector)) as similarity
                FROM "NodeVector" nv
                JOIN "Nodes" n ON nv.node_id = n.node_id
                WHERE nv.node_id != :source_node_id
                AND nv.deleted_at IS NULL
                AND nv."node_vector_chuck_order" = 0
        """
        
        params = {
            "source_embedding": str(list(source_vector.embedding)),
            "source_node_id": str(node_id),
            "threshold": similarity_threshold,
            "limit": limit
        }
        
        if user_id:
            sql += " AND n.created_by = :user_id"
            params["user_id"] = str(user_id)
        
        sql += """
                ORDER BY n.node_id, similarity DESC
            )
            SELECT * FROM node_similarities
            WHERE similarity >= :threshold
            ORDER BY similarity DESC
            LIMIT :limit
        """
        
        result = db.execute(text(sql), params)
        
        return [
            {
                "node_id": str(row.node_id),
                "node_name": row.node_name,
                "node_desc": row.node_desc,
                "similarity": round(float(row.similarity), 4)
            }
            for row in result.fetchall()
        ]
    
    def hybrid_search(
        self,
        query: str,
        db: Session,
        user_id: Optional[UUID] = None,
        limit: int = 10,
        keyword_weight: float = 0.3,
        semantic_weight: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search combining keyword and semantic search.
        
        Args:
            query: Search query
            db: Database session
            user_id: Filter by owner
            limit: Maximum results
            keyword_weight: Weight for keyword matching (0-1)
            semantic_weight: Weight for semantic matching (0-1)
            
        Returns:
            Combined search results
        """
        if not query or not query.strip():
            return []
        
        # Get semantic results
        semantic_results = self.search(
            query=query,
            db=db,
            user_id=user_id,
            limit=limit * 2,  # Get more for merging
            similarity_threshold=0.5
        )
        
        # Get keyword results using ILIKE
        keyword_sql = """
            SELECT DISTINCT
                n.node_id,
                n.node_name,
                n.node_desc,
                nv."node_vector_chuck_id" as chunk_id,
                nv."node_vector_chuck_order" as chunk_order,
                nv."node_content_md_chuck" as content,
                CASE 
                    WHEN LOWER(n.node_name) LIKE LOWER(:query_pattern) THEN 1.0
                    WHEN LOWER(nv."node_content_md_chuck") LIKE LOWER(:query_pattern) THEN 0.8
                    ELSE 0.5
                END as keyword_score
            FROM "NodeVector" nv
            JOIN "Nodes" n ON nv.node_id = n.node_id
            WHERE nv.deleted_at IS NULL
            AND (
                LOWER(n.node_name) LIKE LOWER(:query_pattern)
                OR LOWER(n.node_desc) LIKE LOWER(:query_pattern)
                OR LOWER(nv."node_content_md_chuck") LIKE LOWER(:query_pattern)
            )
        """
        
        params = {"query_pattern": f"%{query}%"}
        
        if user_id:
            keyword_sql += " AND n.created_by = :user_id"
            params["user_id"] = str(user_id)
        
        keyword_sql += " LIMIT :limit"
        params["limit"] = limit * 2
        
        keyword_result = db.execute(text(keyword_sql), params)
        keyword_rows = keyword_result.fetchall()
        
        # Merge and score results
        combined = {}
        
        # Add semantic results
        for item in semantic_results:
            key = (item["node_id"], item["chunk_id"])
            combined[key] = {
                **item,
                "semantic_score": item["similarity"],
                "keyword_score": 0.0
            }
        
        # Add/merge keyword results
        for row in keyword_rows:
            key = (str(row.node_id), str(row.chunk_id))
            if key in combined:
                combined[key]["keyword_score"] = float(row.keyword_score)
            else:
                combined[key] = {
                    "node_id": str(row.node_id),
                    "node_name": row.node_name,
                    "node_desc": row.node_desc,
                    "chunk_id": str(row.chunk_id),
                    "chunk_order": row.chunk_order,
                    "chunk_type": "metadata" if row.chunk_order == 0 else "content",
                    "content": row.content,
                    "semantic_score": 0.0,
                    "keyword_score": float(row.keyword_score)
                }
        
        # Calculate combined score
        results = []
        for item in combined.values():
            item["combined_score"] = (
                semantic_weight * item.get("semantic_score", 0) +
                keyword_weight * item.get("keyword_score", 0)
            )
            item["similarity"] = round(item["combined_score"], 4)
            results.append(item)
        
        # Sort by combined score
        results.sort(key=lambda x: x["combined_score"], reverse=True)
        
        return results[:limit]


# Singleton instance
search_service = SearchService()
