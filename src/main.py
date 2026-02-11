from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager

from src.controllers import (
    agent_router, 
    conversation_router, 
    metadata_router, 
    example_gen_router, 
    job_router,
    node_embedding_router
)
from src.config import settings


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown logic."""
    # === STARTUP ===
    from src.services.job_service import job_service
    from src.services.task_registry import task_registry
    from src.services.job_daemon import job_daemon
    from src.services.rag.node_embedding_service import NodeEmbeddingService

    # 1. Register task handlers
    node_embedding_svc = NodeEmbeddingService()
    task_registry.register(
        "node_content_embedding",
        node_embedding_svc.run_embedding_task
    )

    # 2. Recover orphaned jobs (PROCESSING -> PENDING after crash)
    recovered = job_service.recover_orphaned_jobs()
    if recovered:
        import logging
        logging.getLogger(__name__).warning(f"Recovered {recovered} orphaned jobs")

    # 3. Start Job Daemon
    job_daemon.start()

    yield

    # === SHUTDOWN ===
    job_daemon.stop()
    job_service.shutdown()


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
        lifespan=lifespan
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
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
    app.include_router(node_embedding_router)

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
