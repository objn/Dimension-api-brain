"""
Embedding job registration (typed alternative to POST /jobs for node_content_embedding).
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.database import get_db
from src.dto.rag_dto import EmbeddingProcessRequest
from src.dto.response_dto import success_response
from src.services.rag import node_embedding_service
from src.utils.auth import get_current_user_id

router = APIRouter(
    prefix="/embedding",
    tags=["Embedding"],
)


@router.post(
    "/process",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Register node content embedding job",
    description=(
        "Registers a node_content_embedding job with the same metadata as POST /jobs. "
        "Requires the node to exist in the brain database. Poll GET /jobs/{job_id} for status."
    ),
)
async def register_embedding_process(
    request: EmbeddingProcessRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    from src.services.task_registry import task_registry

    if not task_registry.has("node_content_embedding"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No task handler registered for job type: node_content_embedding",
        )

    start = request.job_start_time or datetime.utcnow()

    try:
        job_id = await node_embedding_service.embed_node(
            node_id=request.node_id,
            user_id=user_id,
            db=db,
            force_reembed=request.force_reembed,
            job_start_time=start,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return success_response({"job_id": job_id})
