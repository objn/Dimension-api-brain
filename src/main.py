from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from src.controllers import agent_router, conversation_router
from src.config import settings


class TrailingSlashMiddleware(BaseHTTPMiddleware):
    """Middleware to normalize URLs by removing trailing slash"""
    
    async def dispatch(self, request: Request, call_next):
        path = request.scope["path"]
        # Remove trailing slash (except for root path "/")
        if path != "/" and path.endswith("/"):
            request.scope["path"] = path.rstrip("/")
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
        redirect_slashes=False
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
