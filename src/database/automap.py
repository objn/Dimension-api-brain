"""
Automap models - Automatically reflect database schema.
Similar to TypeORM's automatic entity discovery.

Usage:
    from src.database.automap import Base, User, Post, etc.
"""
from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import Session

from src.config import settings

# Create engine
engine = create_engine(settings.database_url)

# Reflect the database schema
Base = automap_base()
Base.prepare(autoload_with=engine)

# Access tables as classes (like TypeORM entities)
# Example: User = Base.classes.users
# Example: Post = Base.classes.posts

# You can access all tables through Base.classes
# For example:
# from src.database.automap import Base
# User = Base.classes.users
