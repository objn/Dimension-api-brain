"""
RAG controller.
Semantic search over node chunks (for use in chat RAG and standalone search).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from src.database import get_db
from src.dto.rag_dto import (
    RAGSearchRequest,
    RAGSearchResponse,
    RAGSearchResultItem,
)
from src.dto.response_dto import success_response
from src.utils.auth import get_current_user_id
from src.services.rag import semantic_search_service

router = APIRouter(
    prefix="/rag",
    tags=["RAG"],
)


@router.post(
    "/search",
    status_code=status.HTTP_200_OK,
    summary="Semantic search",
    description="Search over embedded node chunks by natural language query. Returns top-k chunks with similarity scores.",
)
async def rag_search(
    request: RAGSearchRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Run semantic search over Nodevector; used by RAG chat and for testing."""
    try:
        results = semantic_search_service.search(
            db=db,
            query_text=request.query,
            limit=request.limit,
            min_similarity=request.min_similarity,
            scope_node_ids=request.scope_node_ids,
        )
        items = [
            RAGSearchResultItem(
                node_id=r.node_id,
                chunk_id=r.chunk_id,
                node_content_md_chunk=r.node_content_md_chunk,
                similarity=r.similarity,
                node_vector_chunk_order=r.node_vector_chunk_order,
            )
            for r in results
        ]
        response = RAGSearchResponse(count=len(items), results=items)
        return success_response(response.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )
