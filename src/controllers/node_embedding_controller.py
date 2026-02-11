"""
Node Embedding Controller.
API endpoints for RAG operations: embedding, chunks, and search.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional

from src.database import get_db
from src.database.models import Nodes
from src.utils.auth import get_current_user_id
from src.dto.response_dto import success_response
from src.dto.node_embedding_dto import (
    EmbedNodeRequest,
    EmbedNodeResponse,
    EmbeddingStatusResponse,
    NodeChunksResponse,
    ChunkResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SearchInNodeRequest,
    SearchInNodeResponse,
    RelatedNodesResponse,
    RelatedNodeItem,
    HybridSearchRequest
)
from src.services.rag import node_embedding_service, search_service
from src.services.job_service import job_service

router = APIRouter(
    prefix="/nodes",
    tags=["Node Embedding & Search"]
)


# ============================================================================
# Embedding Endpoints
# ============================================================================

@router.post(
    "/{node_id}/embed",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start node embedding",
    description="Start a background job to embed a node's content. Returns job ID for tracking."
)
async def embed_node(
    node_id: UUID,
    request: EmbedNodeRequest = EmbedNodeRequest(),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    Start embedding job for a node.
    
    - Creates chunks from node_name, node_desc, and node_content_md
    - chunk_order=0 contains metadata (name + description)
    - chunk_order=1+ contains content chunks
    - Uses hash comparison to only re-embed changed chunks
    """
    try:
        # Verify node exists and user has access
        node = db.query(Nodes).filter(Nodes.node_id == node_id).first()
        if not node:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Node with ID {node_id} not found"
            )
        
        if node.created_by != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to embed this node"
            )
        
        # Start embedding job
        job_id = await node_embedding_service.embed_node(
            node_id=node_id,
            user_id=user_id,
            db=db,
            force_reembed=request.force_reembed
        )
        
        return success_response(
            EmbedNodeResponse(
                job_id=job_id,
                node_id=node_id,
                status="PENDING",
                message="Embedding job started"
            ).model_dump()
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start embedding: {str(e)}"
        )


@router.get(
    "/{node_id}/embed/status/{job_id}",
    status_code=status.HTTP_200_OK,
    summary="Get embedding job status",
    description="Get the current status and progress of an embedding job"
)
async def get_embedding_status(
    node_id: UUID,
    job_id: UUID,
    user_id: UUID = Depends(get_current_user_id)
):
    """Get embedding job status with progress information."""
    try:
        job_info = job_service.get_job_info(job_id)
        
        if not job_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job with ID {job_id} not found"
            )
        
        # Extract metadata
        metadata = job_info.get("metadata", {})
        
        response = EmbeddingStatusResponse(
            job_id=job_id,
            node_id=node_id,
            status=job_info.get("status", "UNKNOWN"),
            stage=metadata.get("stage"),
            progress=metadata.get("progress", 0),
            message=metadata.get("message"),
            result=metadata.get("result")
        )
        
        return success_response(response.model_dump())
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job status: {str(e)}"
        )


@router.delete(
    "/{node_id}/embed/{job_id}",
    status_code=status.HTTP_200_OK,
    summary="Cancel embedding job",
    description="Cancel a running embedding job"
)
async def cancel_embedding(
    node_id: UUID,
    job_id: UUID,
    user_id: UUID = Depends(get_current_user_id)
):
    """Cancel a running embedding job."""
    try:
        success = job_service.interrupt_job(job_id, reason="User cancelled")
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not cancel job. It may have already completed."
            )
        
        return success_response({
            "job_id": str(job_id),
            "node_id": str(node_id),
            "status": "INTERRUPTED",
            "message": "Embedding job cancelled"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel job: {str(e)}"
        )


# ============================================================================
# Chunk Endpoints
# ============================================================================

@router.get(
    "/{node_id}/chunks",
    status_code=status.HTTP_200_OK,
    summary="Get node chunks",
    description="Get all embedding chunks for a node"
)
async def get_node_chunks(
    node_id: UUID,
    include_embeddings: bool = Query(
        default=False,
        description="Include embedding vectors in response"
    ),
    include_deleted: bool = Query(
        default=False,
        description="Include soft-deleted chunks"
    ),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    Get all chunks for a node.
    
    - chunk_order=0 is the metadata chunk (node_name + node_desc)
    - chunk_order=1+ are content chunks from node_content_md
    """
    try:
        # Verify node exists
        node = db.query(Nodes).filter(Nodes.node_id == node_id).first()
        if not node:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Node with ID {node_id} not found"
            )
        
        chunks = node_embedding_service.get_node_chunks(
            node_id=node_id,
            db=db,
            include_embeddings=include_embeddings,
            include_deleted=include_deleted
        )
        
        return success_response({
            "node_id": str(node_id),
            "node_name": node.node_name,
            "total_chunks": len(chunks),
            "chunks": chunks
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get chunks: {str(e)}"
        )


@router.get(
    "/chunks/{chunk_id}",
    status_code=status.HTTP_200_OK,
    summary="Get chunk by ID",
    description="Get a specific chunk by its ID"
)
async def get_chunk_by_id(
    chunk_id: UUID,
    include_embedding: bool = Query(default=False),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Get a specific chunk by ID."""
    try:
        chunk = node_embedding_service.get_chunk_by_id(
            chunk_id=chunk_id,
            db=db,
            include_embedding=include_embedding
        )
        
        if not chunk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chunk with ID {chunk_id} not found"
            )
        
        return success_response(chunk)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get chunk: {str(e)}"
        )


# ============================================================================
# Search Endpoints
# ============================================================================

@router.post(
    "/search",
    status_code=status.HTTP_200_OK,
    summary="Semantic search",
    description="Search across all nodes using semantic similarity"
)
async def search_nodes(
    request: SearchRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    Semantic search across all accessible nodes.
    
    Returns chunks with similarity scores, sorted by relevance.
    """
    try:
        results = search_service.search(
            query=request.query,
            db=db,
            user_id=user_id,
            limit=request.limit,
            similarity_threshold=request.similarity_threshold,
            include_content=request.include_content,
            include_metadata_chunks=request.include_metadata_chunks
        )
        
        return success_response(
            SearchResponse(
                query=request.query,
                total_results=len(results),
                results=[SearchResultItem(**r) for r in results]
            ).model_dump()
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get(
    "/{node_id}/search",
    status_code=status.HTTP_200_OK,
    summary="Search within node",
    description="Search within a specific node's chunks"
)
async def search_in_node(
    node_id: UUID,
    query: str = Query(..., min_length=1, max_length=1000),
    limit: int = Query(default=5, ge=1, le=50),
    include_metadata: bool = Query(default=True),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Search within a specific node's chunks."""
    try:
        # Verify node exists
        node = db.query(Nodes).filter(Nodes.node_id == node_id).first()
        if not node:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Node with ID {node_id} not found"
            )
        
        results = search_service.search_in_node(
            query=query,
            node_id=node_id,
            db=db,
            limit=limit,
            include_metadata=include_metadata
        )
        
        return success_response({
            "node_id": str(node_id),
            "node_name": node.node_name,
            "query": query,
            "total_results": len(results),
            "results": results
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get(
    "/{node_id}/related",
    status_code=status.HTTP_200_OK,
    summary="Find related nodes",
    description="Find nodes similar to a given node based on content"
)
async def get_related_nodes(
    node_id: UUID,
    limit: int = Query(default=10, ge=1, le=50),
    similarity_threshold: float = Query(default=0.5, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Find nodes related to a given node based on content similarity."""
    try:
        # Verify node exists
        node = db.query(Nodes).filter(Nodes.node_id == node_id).first()
        if not node:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Node with ID {node_id} not found"
            )
        
        related = search_service.find_related_nodes(
            node_id=node_id,
            db=db,
            limit=limit,
            similarity_threshold=similarity_threshold,
            user_id=user_id
        )
        
        return success_response(
            RelatedNodesResponse(
                source_node_id=node_id,
                total_results=len(related),
                related_nodes=[RelatedNodeItem(**r) for r in related]
            ).model_dump()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to find related nodes: {str(e)}"
        )


@router.post(
    "/search/hybrid",
    status_code=status.HTTP_200_OK,
    summary="Hybrid search",
    description="Combined keyword and semantic search"
)
async def hybrid_search(
    request: HybridSearchRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    Hybrid search combining keyword matching and semantic similarity.
    
    Useful when you want exact keyword matches boosted alongside semantic matches.
    """
    try:
        results = search_service.hybrid_search(
            query=request.query,
            db=db,
            user_id=user_id,
            limit=request.limit,
            keyword_weight=request.keyword_weight,
            semantic_weight=request.semantic_weight
        )
        
        return success_response({
            "query": request.query,
            "total_results": len(results),
            "keyword_weight": request.keyword_weight,
            "semantic_weight": request.semantic_weight,
            "results": results
        })
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Hybrid search failed: {str(e)}"
        )
