"""
LLM utility endpoints (e.g. suggest relation between two entities).
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
    summary="Suggest one relation parent→child (from RelationTypes)",
    description=(
        "Given parent_id/child_id and type_of_parent/type_of_child (node, workspace, file), loads text for each side, "
        "loads allowed relation_type_id from RelationTypes, and uses the LLM to pick exactly one type with a short explanation. "
        "File sides use DB metadata only (no document parse). Each entity must be owned by the caller (created_by)."
    ),
)
async def post_suggest_relation(
    request: SuggestRelationRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Suggest a single directed relation from parent to child using only types defined in RelationTypes."""
    try:
        one = suggest_relation(
            db=db,
            parent_id=request.parent_id,
            child_id=request.child_id,
            type_of_parent=request.type_of_parent,
            type_of_child=request.type_of_child,
            user_id=user_id,
            provider="openai",
        )
        response = SuggestRelationResponse(suggestion=SuggestRelationItem(**one))
        return success_response(response.model_dump())
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e) or "Forbidden",
        ) from e
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
