"""
LLM utility endpoints (e.g. suggest relation between two nodes).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from src.database import get_db
from src.dto.llm_dto import SuggestRelationRequest, SuggestRelationResponse, SuggestRelationItem
from src.dto.response_dto import success_response
from src.utils.auth import get_current_user_id
from src.services.llm_suggest_relation_service import suggest_relations

router = APIRouter(
    prefix="",
    tags=["LLM"],
)


@router.post(
    "/suggest-relation",
    status_code=status.HTTP_200_OK,
    summary="Suggest relations between two nodes",
    description="Given two node UUIDs, read their content and use LLM to suggest 3-5 possible relations for the user to choose from.",
)
async def post_suggest_relation(
    request: SuggestRelationRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Suggest 3-5 relations between content of node_a and node_b."""
    try:
        suggestions = suggest_relations(
            db=db,
            node_a_id=request.node_a,
            node_b_id=request.node_b,
            provider="openai",
        )
        response = SuggestRelationResponse(
            suggestions=[SuggestRelationItem(**s) for s in suggestions]
        )
        return success_response(response.model_dump())
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error suggesting relations: {str(e)}",
        ) from e
