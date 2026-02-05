"""
DTOs for Example Generation operations.
Request and response models with validation.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from datetime import datetime
from uuid import UUID

from .base_dto import BaseResponseModel


class ExampleGenRequest(BaseModel):
    """Request body for generating example data"""
    table_name: str = Field(..., min_length=1, max_length=255, description="Name of the database table")
    prompt: str = Field(..., min_length=1, description="Prompt describing the data to generate")
    execute_insert: bool = Field(default=False, description="Whether to execute the INSERT query (only INSERT allowed, no DELETE/DROP)")
    agent_prompt: Optional[str] = Field(None, description="Optional agent system prompt to customize data generation behavior")

    class Config:
        json_schema_extra = {
            "example": {
                "table_name": "Users",
                "prompt": "Generate 5 sample users with realistic names and email addresses",
                "execute_insert": False,
                "agent_prompt": "You are a helpful assistant that generates realistic test data for software development."
            }
        }


class ExampleGenResponse(BaseResponseModel):
    """Response model for example generation"""
    success: bool
    table_name: str
    thought_process: Optional[str] = None
    generated_data: Optional[List[Dict[str, Any]]] = None
    insert_query: Optional[str] = None
    record_count: Optional[int] = None
    executed: Optional[bool] = None
    inserted_records: Optional[int] = None
    error: Optional[str] = None
    raw_response: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "table_name": "Users",
                "thought_process": "Generated 5 diverse users with realistic data...",
                "generated_data": [
                    {
                        "user_id": "123e4567-e89b-12d3-a456-426614174000",
                        "username": "john_doe",
                        "email": "john@example.com"
                    }
                ],
                "insert_query": "INSERT INTO Users (user_id, username, email) VALUES ...",
                "record_count": 5,
                "executed": True,
                "inserted_records": 5,
                "error": None,
                "raw_response": "{...}"
            }
        }