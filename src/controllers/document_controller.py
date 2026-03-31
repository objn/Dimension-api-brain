"""
Document controller.
File upload and import (store file, create Files row).
Process: parse, reformat, create node, trigger embedding.
"""
import uuid
from pathlib import Path
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Header
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.database import get_db
from src.database.models import Files
from src.dto.document_dto import (
    DocumentImportResponse,
    DocumentProcessRequest,
    ALLOWED_EXTENSIONS,
    ALLOWED_IMPORT_MIMES,
)
from src.dto.response_dto import success_response
from src.utils.auth import get_current_user_id
from src.repositories.file_repository import FileRepository
from src.services.document_service import JOB_TYPE_PROCESS_DOCUMENT
from src.services.job_service import job_service

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


def _allowed_file(filename: str, content_type: str | None) -> bool:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False
    if content_type and content_type.split(";")[0].strip().lower() not in ALLOWED_IMPORT_MIMES:
        # Allow by extension even if client sends wrong mime
        return True
    return True


@router.post(
    "/import",
    status_code=status.HTTP_201_CREATED,
    summary="Import a document",
    description="Upload a file (.docx, .pdf, .jpg, .png). File is stored and a Files record is created only. To parse and create nodes, call POST /documents/{file_id}/process.",
)
async def import_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Upload a single file; validate type, store on disk, create Files row."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing filename",
        )
    if not _allowed_file(file.filename, file.content_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4()
    safe_name = f"{file_id}_{file.filename}"
    file_path = (upload_dir / safe_name).resolve()

    try:
        contents = await file.read()
        file_size = len(contents)
        file_path.write_bytes(contents)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}",
        )

    mime_type = file.content_type or "application/octet-stream"
    if mime_type and ";" in mime_type:
        mime_type = mime_type.split(";")[0].strip()

    now = datetime.utcnow()
    file_entity = Files(
        file_id=file_id,
        file_name=file.filename,
        file_size=file_size,
        mime_type=mime_type,
        created_at=now,
        created_by=user_id,
        file_path=str(file_path),
    )
    repo = FileRepository(db)
    created = repo.create(file_entity)

    response = DocumentImportResponse(
        file_id=created.file_id,
        file_name=created.file_name,
        file_size=created.file_size,
        mime_type=created.mime_type,
        file_path=created.file_path,
        created_at=created.created_at,
    )
    return success_response(response.model_dump())


@router.post(
    "/{file_id}/process",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Process imported document (async)",
    description="Register a document processing job. Requires workspace_id in body when create_node=true; send Authorization header for BACKEND_SERVER /nodes and /relations. Poll GET /jobs/{job_id} for status.",
)
async def process_imported_document(
    file_id: UUID,
    request: DocumentProcessRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Register a background job to parse document, create node, and trigger embedding. Returns job_id; poll job status for result."""
    from datetime import datetime

    repo = FileRepository(db)
    file_entity = repo.find_one_by_id(file_id)
    if not file_entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if file_entity.created_by != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to process this file")

    if request.create_node:
        if request.workspace_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="workspace_id is required when create_node=true",
            )
        if not authorization or not authorization.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header is required when create_node=true (for BACKEND_SERVER /nodes and /relations)",
            )

    metadata = {
        "file_id": str(file_id),
        "workspace_id": str(request.workspace_id) if request.workspace_id else None,
        "reformat_options": request.reformat_options or [],
        "llm_provider": request.llm_provider or "openai",
        "create_node": request.create_node,
        "max_pages_per_call": request.max_pages_per_call if request.max_pages_per_call is not None else 5,
    }
    if authorization:
        metadata["authorization"] = authorization.strip()

    job_id = await job_service.register_job(
        user_id=user_id,
        job_type=JOB_TYPE_PROCESS_DOCUMENT,
        metadata=metadata,
        job_start_time=datetime.utcnow(),
        db=db,
    )
    # Keep response minimal: client can poll GET /jobs/{job_id} for status + metadata.
    return success_response({"job_id": job_id})
