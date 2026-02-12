from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from src.config import settings

# Create SQLAlchemy engine with UTF-8 encoding
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # Enable connection health checks
    pool_size=5,
    max_overflow=10,
    echo=settings.environment == "development",  # Log SQL in development
    connect_args={"client_encoding": "utf8"},
)

# Silent engine for background tasks (no SQL logging)
silent_engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=2,
    max_overflow=5,
    echo=False,  # Never log SQL
    connect_args={"client_encoding": "utf8"},
)

# Set client encoding to UTF-8 on connection
@event.listens_for(engine, "connect")
def set_client_encoding(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("SET client_encoding TO 'UTF8'")
    cursor.close()

@event.listens_for(silent_engine, "connect")
def set_client_encoding_silent(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("SET client_encoding TO 'UTF8'")
    cursor.close()

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
SilentSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=silent_engine)

# Create Base class for models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency function to get database session.

    Usage in FastAPI:
        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_silent_db() -> Generator[Session, None, None]:
    """
    Get database session without SQL logging.
    Used for background tasks like JobDaemon.
    """
    db = SilentSessionLocal()
    try:
        yield db
    finally:
        db.close()
