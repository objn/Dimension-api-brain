"""
FileVector controller.
Fetch file vector chunk by composite id (conversation_id + chunk_id).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from src.database import get_db
from src.dto.response_dto import success_response
from src.dto.filevector_dto import FilevectorResponse
from src.repositories.file_repository import FileRepository
from src.repositories.file_vector_repository import FileVectorRepository
from src.utils.auth import get_current_user_id

router = APIRouter(
    prefix="/filevector",
    tags=["FileVector"],
)


@router.get(
    "/getbyid",
    status_code=status.HTTP_200_OK,
    summary="Get FileVector chunk by composite id",
    description="Fetch a single FileVector row by conversation_id + chunk_id (file_vector_chunk_id).",
)
async def get_filevector_by_id(
    conversation_id: UUID,
    chunk_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        repo = FileVectorRepository(db)
        row = repo.find_one_by_composite_id(
            conversation_id=conversation_id, chunk_id=chunk_id
        )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="FileVector not found",
            )

        if getattr(row, "created_by", None) != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this filevector",
            )

        result = FilevectorResponse.model_validate(row)
        try:
            file_repo = FileRepository(db)
            file_entity = file_repo.find_one_by_id(getattr(row, "file_id", None))
            if file_entity is not None and getattr(file_entity, "file_name", None):
                result.file_name = str(file_entity.file_name)
        except Exception:
            # Best-effort enrichment; keep core chunk response stable.
            pass
        return success_response(result.model_dump(by_alias=True))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching filevector: {str(e)}",
        )
