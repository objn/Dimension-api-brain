from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager

from src.config import settings
from src.controllers import (
    agent_router,
    conversation_router,
    metadata_router,
    example_gen_router,
    job_router,
    embedding_router,
    rag_router,
    document_router,
    llm_router,
    search_router,
    nodevector_router,
)


def _register_job_tasks() -> None:
    """Register job task handlers so the job daemon can run them."""
    from src.services.task_registry import task_registry
    from src.services.rag import node_embedding_service
    from src.services.document_service import run_process_document_task

    task_registry.register("node_content_embedding", node_embedding_service.run_embedding_task)
    task_registry.register("process_document", run_process_document_task)


def _ensure_job_types() -> None:
    """Ensure required job type rows exist in JobTypes so Jobs.job_type FK does not fail."""
    from src.database.connection import SilentSessionLocal
    from src.database.models import Jobtypes

    required = ("process_document", "node_content_embedding")
    db = SilentSessionLocal()
    try:
        for job_type_id in required:
            if db.query(Jobtypes).filter(Jobtypes.Job_type_id == job_type_id).first() is None:
                db.add(Jobtypes(Job_type_id=job_type_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


class TrailingSlashMiddleware(BaseHTTPMiddleware):
    """Middleware to normalize URLs"""
    
    async def dispatch(self, request: Request, call_next):
        path = request.scope["path"]
        
        # Strip /llm prefix if present (reverse proxy didn't strip it)
        if path.startswith("/llm"):
            path = path[4:] or "/"  # Remove "/llm", default to "/" if empty
        
        # Remove trailing slash (except for root path "/")
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        
        request.scope["path"] = path
        return await call_next(request)


def create_app() -> FastAPI:
    """Application factory"""

    app = FastAPI(
        title="Dimension API Brain",
        description="LLM Service API with MVC Architecture",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        root_path="/llm",
        redirect_slashes=False,
    )

    @app.on_event("startup")
    def startup_register_tasks():
        _ensure_job_types()
        _register_job_tasks()
        if getattr(settings, "job_daemon_auto_start", True):
            from src.services.job_daemon import job_daemon
            job_daemon.start()

    # CORS middleware
    if settings.environment == "production":
        # Production: specific origins, allow credentials
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        # Development: allow all origins, no credentials
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    # Trailing slash middleware (normalize URLs without redirect)
    app.add_middleware(TrailingSlashMiddleware)
    
    # Include routers
    app.include_router(agent_router)
    app.include_router(conversation_router)
    app.include_router(metadata_router)
    app.include_router(example_gen_router)
    app.include_router(job_router)
    app.include_router(embedding_router)
    app.include_router(rag_router)
    app.include_router(document_router)
    app.include_router(llm_router)
    app.include_router(search_router)
    app.include_router(nodevector_router)

    # Root endpoint
    @app.get("/", status_code=status.HTTP_200_OK)
    async def root():
        return {
            "name": "Dimension API Brain",
            "version": "1.0.0",
            "environment": settings.environment
        }

    @app.get("/health", status_code=status.HTTP_200_OK)
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
