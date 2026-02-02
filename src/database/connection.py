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

# Set client encoding to UTF-8 on connection
@event.listens_for(engine, "connect")
def set_client_encoding(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("SET client_encoding TO 'UTF8'")
    cursor.close()

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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
