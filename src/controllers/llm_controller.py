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
from src.services.llm_suggest_relation_service import suggest_relation

router = APIRouter(
    prefix="",
    tags=["LLM"],
)


@router.post(
    "/suggest-relation",
    status_code=status.HTTP_200_OK,
    summary="Suggest one relation between two nodes (from RelationTypes)",
    description=(
        "Given two node UUIDs, loads allowed relation_type_id values from the RelationTypes table, "
        "reads node content, and uses the LLM to pick exactly one of those types with a short explanation."
    ),
)
async def post_suggest_relation(
    request: SuggestRelationRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Suggest a single relation between node_a and node_b using only types defined in RelationTypes."""
    try:
        one = suggest_relation(
            db=db,
            node_a_id=request.node_a,
            node_b_id=request.node_b,
            provider="openai",
        )
        response = SuggestRelationResponse(suggestion=SuggestRelationItem(**one))
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
            detail=f"Error suggesting relation: {str(e)}",
        ) from e
