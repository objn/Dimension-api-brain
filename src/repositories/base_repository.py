"""
Base repository class (like TypeORM Repository).
Provides common CRUD operations for all entities.
"""
from typing import Generic, TypeVar, Type, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, update, delete
from uuid import UUID

from src.database import Base

T = TypeVar('T', bound=Base)


class BaseRepository(Generic[T]):
    """
    Base repository with common CRUD operations.
    Similar to TypeORM's Repository pattern.
    """

    def __init__(self, model: Type[T], db: Session):
        self.model = model
        self.db = db

    def find_all(self) -> List[T]:
        """
        Find all records.
        Similar to TypeORM's repository.find()
        """
        return self.db.query(self.model).all()

    def find_one_by_id(self, id: UUID) -> Optional[T]:
        """
        Find one record by primary key.
        Similar to TypeORM's repository.findOne()
        """
        return self.db.query(self.model).filter(
            getattr(self.model, self._get_pk_name()) == id
        ).first()

    def find_by(self, **filters) -> List[T]:
        """
        Find records by filters.
        Similar to TypeORM's repository.find({ where: {...} })

        Example:
            repo.find_by(email="test@example.com", active=True)
        """
        query = self.db.query(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key):
                query = query.filter(getattr(self.model, key) == value)
        return query.all()

    def find_one_by(self, **filters) -> Optional[T]:
        """
        Find one record by filters.
        Similar to TypeORM's repository.findOne({ where: {...} })
        """
        query = self.db.query(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key):
                query = query.filter(getattr(self.model, key) == value)
        return query.first()

    def create(self, entity: T) -> T:
        """
        Create a new record.
        Similar to TypeORM's repository.save()
        """
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def update_by_id(self, id: UUID, data: dict) -> Optional[T]:
        """
        Update a record by ID.
        Similar to TypeORM's repository.update()
        """
        entity = self.find_one_by_id(id)
        if not entity:
            return None

        for key, value in data.items():
            if hasattr(entity, key):
                setattr(entity, key, value)

        self.db.commit()
        self.db.refresh(entity)
        return entity

    def delete_by_id(self, id: UUID) -> bool:
        """
        Delete a record by ID.
        Similar to TypeORM's repository.delete()
        """
        entity = self.find_one_by_id(id)
        if not entity:
            return False

        self.db.delete(entity)
        self.db.commit()
        return True

    def count(self) -> int:
        """
        Count all records.
        Similar to TypeORM's repository.count()
        """
        return self.db.query(self.model).count()

    def count_by(self, **filters) -> int:
        """
        Count records by filters.
        Similar to TypeORM's repository.count({ where: {...} })
        """
        query = self.db.query(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key):
                query = query.filter(getattr(self.model, key) == value)
        return query.count()

    def exists_by_id(self, id: UUID) -> bool:
        """
        Check if record exists by ID.
        Similar to TypeORM's repository.exist()
        """
        return self.find_one_by_id(id) is not None

    def exists_by(self, **filters) -> bool:
        """
        Check if record exists by filters.
        """
        return self.find_one_by(**filters) is not None

    def _get_pk_name(self) -> str:
        """Get the primary key column name"""
        return self.model.__table__.primary_key.columns.keys()[0]
