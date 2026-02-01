"""
Authentication DTO models.
Authentication is handled by external service.
"""
from pydantic import BaseModel, Field
from uuid import UUID


class CurrentUserResponse(BaseModel):
    """Current authenticated user response"""
    user_id: UUID = Field(..., description="Authenticated user ID from JWT token")
    message: str = Field(default="Token is valid", description="Status message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "message": "Token is valid"
            }
        }
