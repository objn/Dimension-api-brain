"""
NodeVector controller.
Fetch node vector chunk by composite id (node_id + chunk_id).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from src.database import get_db
from src.dto.response_dto import success_response
from src.dto.nodevector_dto import NodevectorResponse
from src.repositories.node_repository import NodeRepository
from src.repositories.nodevector_repository import NodevectorRepository
from src.utils.auth import get_current_user_id

router = APIRouter(
    prefix="/nodevector",
    tags=["NodeVector"],
)


@router.get(
    "/getbyid",
    status_code=status.HTTP_200_OK,
    summary="Get NodeVector chunk by composite id",
    description="Fetch a single NodeVector row by node_id + chunk_id (node_vector_chunk_id).",
)
async def get_nodevector_by_id(
    node_id: UUID,
    chunk_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        repo = NodevectorRepository(db)
        row = repo.find_one_by_composite_id(node_id=node_id, chunk_id=chunk_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NodeVector not found")

        if getattr(row, "created_by", None) != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to access this nodevector")

        result = NodevectorResponse.model_validate(row)
        try:
            node_repo = NodeRepository(db)
            node_entity = node_repo.find_one_by_id(getattr(row, "node_id", None))
            if node_entity is not None and getattr(node_entity, "node_name", None):
                result.node_name = str(node_entity.node_name)
        except Exception:
            # Best-effort enrichment; keep core chunk response stable.
            pass
        return success_response(result.model_dump(by_alias=True))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching nodevector: {str(e)}",
        )

