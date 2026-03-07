"""
DTOs for document/file import.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from typing import Literal


ReformatOption = Literal["rearrange", "fill_missing_ai", "to_bullet_points", "to_table", "summarize"]


# Allowed MIME types for import
ALLOWED_IMPORT_MIMES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/jpg",
}
ALLOWED_EXTENSIONS = {".docx", ".pdf", ".jpg", ".jpeg", ".png"}


class DocumentImportResponse(BaseModel):
    """Response after importing a document (file stored + metadata). When auto_process is true, job_id is included."""
    file_id: UUID
    file_name: str
    file_size: int
    mime_type: str
    file_path: str
    created_at: Optional[datetime] = None
    job_id: Optional[UUID] = Field(default=None, description="Process job ID when processing was started automatically; poll GET /jobs/{job_id}")


class DocumentProcessRequest(BaseModel):
    """Request to process an imported file: parse, optional reformat, create node, trigger embedding."""
    reformat_options: Optional[List[ReformatOption]] = Field(
        default_factory=list,
        description="Optional: rearrange, fill_missing_ai, to_bullet_points, to_table, summarize (multiple or none)"
    )
    llm_provider: Optional[Literal["openai", "gemini", "anthropic"]] = Field(default="openai")
    create_node: bool = Field(default=True, description="Create a Node from extracted content and run embedding")
    use_llm_extract: bool = Field(
        default=False,
        description="If true, use LLM to extract/clean/structure content; when local extraction fails (e.g. PDF) uses vision LLM in batches"
    )
    max_pages_per_call: Optional[int] = Field(
        default=5,
        ge=1,
        le=20,
        description="When using LLM vision for PDFs: pages per LLM call (default 5). Use 1 for OCR-style one page per call."
    )
    translate_to: Optional[Literal["en", "th"]] = Field(
        default=None,
        description="If 'en' translate content to English; if 'th' translate to Thai; if null do not translate"
    )


class DocumentProcessResponse(BaseModel):
    """Response after registering process job (async). job_id is returned immediately; node_id/node_name available in job metadata when status=SUCCESS."""
    file_id: UUID
    node_id: Optional[UUID] = Field(default=None, description="Set when job completes successfully (or poll GET /jobs/{job_id})")
    node_name: Optional[str] = Field(default=None, description="Set when job completes successfully")
    job_id: Optional[UUID] = Field(default=None, description="Process job ID; poll for status and result")
