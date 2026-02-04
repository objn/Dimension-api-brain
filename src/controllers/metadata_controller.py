"""
Metadata CRUD controller.
All operations use ORM - no raw SQL queries.
Users can only access their own data via JWT user_id.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime

from src.database import get_db
from src.repositories.metadata_repository import MetadataRepository
from src.database.models import Metadatas
from src.dto.metadata_dto import (
    MetadataCreateRequest,
    MetadataUpdateRequest,
    MetadataResponse,
    MetadataListResponse
)
from src.dto.response_dto import success_response, error_response
from src.utils.auth import get_current_user_id

router = APIRouter(
    prefix="/metadatas",
    tags=["Metadatas"]
)


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Get all metadatas",
    description="Retrieve all metadatas created by the authenticated user"
)
async def get_all_metadatas(
    limit: Optional[int] = None,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Get all metadatas created by the authenticated user - uses ORM query"""
    try:
        repo = MetadataRepository(db)
        metadatas = repo.find_by_creator(user_id)

        if limit:
            metadatas = metadatas[:limit]

        result = MetadataListResponse(
            count=len(metadatas),
            metadatas=[MetadataResponse.model_validate(metadata) for metadata in metadatas]
        )
        return success_response(result.model_dump())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching metadatas: {str(e)}"
        )


@router.get(
    "/{metadata_id}",
    status_code=status.HTTP_200_OK,
    summary="Get metadata by ID",
    description="Retrieve a single metadata by ID (only if created by authenticated user)"
)
async def get_metadata_by_id(
    metadata_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Get metadata by ID - uses ORM, only returns if user owns the metadata"""
    try:
        repo = MetadataRepository(db)
        metadata = repo.find_one_by_id(metadata_id)

        if not metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Metadata with ID {metadata_id} not found"
            )

        if metadata.created_by != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this metadata"
            )

        result = MetadataResponse.model_validate(metadata)
        return success_response(result.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching metadata: {str(e)}"
        )


@router.get(
    "/by-entity/{entity_id}",
    status_code=status.HTTP_200_OK,
    summary="Get metadatas by entity ID",
    description="Retrieve all metadatas for a specific entity (only user's own metadatas)"
)
async def get_metadatas_by_entity(
    entity_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Get metadatas by entity ID - filtered by user's own metadatas"""
    try:
        repo = MetadataRepository(db)
        metadatas = repo.find_by_creator_and_metadata_of(user_id, entity_id)

        result = MetadataListResponse(
            count=len(metadatas),
            metadatas=[MetadataResponse.model_validate(metadata) for metadata in metadatas]
        )
        return success_response(result.model_dump())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching metadatas: {str(e)}"
        )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create new metadata",
    description="Create a new metadata using ORM (requires authentication)"
)
async def create_metadata(
    request: MetadataCreateRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Create metadata - uses ORM with authenticated user_id"""
    try:
        repo = MetadataRepository(db)

        # Create new metadata entity
        new_metadata = Metadatas(
            metadata_id=uuid4(),
            metadata_of=request.metadata_of,
            metadata_json=request.metadata_json,
            content_to_summarize=request.content_to_summarize,
            created_at=datetime.utcnow(),
            created_by=user_id,
            updated_at=datetime.utcnow(),
            updated_by=user_id
        )

        created_metadata = repo.create(new_metadata)
        result = MetadataResponse.model_validate(created_metadata)
        return success_response(result.model_dump())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating metadata: {str(e)}"
        )


@router.put(
    "/{metadata_id}",
    status_code=status.HTTP_200_OK,
    summary="Update metadata",
    description="Update an existing metadata (only if created by authenticated user)"
)
async def update_metadata(
    metadata_id: UUID,
    request: MetadataUpdateRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Update metadata - uses ORM, only allows update if user owns the metadata"""
    try:
        repo = MetadataRepository(db)
        metadata = repo.find_one_by_id(metadata_id)

        if not metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Metadata with ID {metadata_id} not found"
            )

        if metadata.created_by != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this metadata"
            )

        # Build update data (only include fields that were provided)
        update_data = {}
        if request.metadata_of is not None:
            update_data["metadata_of"] = request.metadata_of
        if request.metadata_json is not None:
            update_data["metadata_json"] = request.metadata_json
        if request.content_to_summarize is not None:
            update_data["content_to_summarize"] = request.content_to_summarize

        # Always update audit fields
        update_data["updated_at"] = datetime.utcnow()
        update_data["updated_by"] = user_id

        updated_metadata = repo.update_by_id(metadata_id, update_data)
        result = MetadataResponse.model_validate(updated_metadata)
        return success_response(result.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating metadata: {str(e)}"
        )


@router.delete(
    "/{metadata_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete metadata",
    description="Delete a metadata (only if created by authenticated user)"
)
async def delete_metadata(
    metadata_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Delete metadata - uses ORM, only allows delete if user owns the metadata"""
    try:
        repo = MetadataRepository(db)
        metadata = repo.find_one_by_id(metadata_id)

        if not metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Metadata with ID {metadata_id} not found"
            )

        if metadata.created_by != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this metadata"
            )

        repo.delete_by_id(metadata_id)
        return success_response({"message": f"Metadata {metadata_id} deleted successfully"})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting metadata: {str(e)}"
        )
