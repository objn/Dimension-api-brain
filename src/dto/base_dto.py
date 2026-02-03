"""
Base DTO model with ISO-8601 datetime serialization.
All response models should inherit from this.
"""
from pydantic import BaseModel, ConfigDict, model_serializer
from datetime import datetime
from typing import Any


def serialize_datetime(value: Any) -> Any:
    """Recursively serialize datetime to ISO-8601 format with Z suffix"""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    elif isinstance(value, dict):
        return {k: serialize_datetime(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [serialize_datetime(item) for item in value]
    return value


class BaseResponseModel(BaseModel):
    """Base model with ISO-8601 datetime format (with Z suffix)"""
    
    model_config = ConfigDict(from_attributes=True)
    
    @model_serializer(mode='wrap')
    def serialize_model(self, handler) -> dict:
        data = handler(self)
        return serialize_datetime(data)
