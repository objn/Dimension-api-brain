from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal, Optional
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Server
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    environment: str = Field(default="development", alias="ENVIRONMENT")

    # Database
    database_url: str = Field(..., alias="DATABASE_URL")

    # JWT Authentication
    jwt_secret: str = Field(default="your-secret-key-change-in-production", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")

    # OpenAI Configuration
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4", alias="OPENAI_MODEL")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1", alias="OPENAI_BASE_URL"
    )

    # Google Gemini Configuration
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-pro", alias="GEMINI_MODEL")
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1",
        alias="GEMINI_BASE_URL",
    )

    # Anthropic Configuration
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(
        default="claude-3-5-sonnet-20241022", alias="ANTHROPIC_MODEL"
    )
    anthropic_base_url: str = Field(
        default="https://api.anthropic.com/v1", alias="ANTHROPIC_BASE_URL"
    )

    # Job Daemon Configuration
    job_worker_num: int = Field(default=3, alias="JOB_WORKER_NUM")
    job_poll_interval: int = Field(default=5, alias="JOB_POLL_INTERVAL")
    job_worker_break_off_time: int = Field(default=30, alias="JOB_WORKER_BREAK_OFF_TIME")
    job_daemon_verbose: bool = Field(default=False, alias="JOB_DAEMON_VERBOSE")
    job_daemon_auto_start: bool = Field(default=True, alias="JOB_DAEMON_AUTO_START")

    # File / Document upload
    upload_dir: str = Field(default="uploads", alias="UPLOAD_DIR")

    class Config:
        env_file = ".env"
        extra = "ignore"
        
# Singleton instance
settings = Settings()
