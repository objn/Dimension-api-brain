"""
Standardized API response models
"""
from pydantic import BaseModel, Field
from typing import Any, Optional, TypeVar, Generic

T = TypeVar('T')


class ApiResponse(BaseModel, Generic[T]):
    """Standardized API response wrapper"""
    status: bool = Field(..., description="Request success status")
    resultData: T = Field(..., description="Response data")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": True,
                "resultData": {}
            }
        }


class ErrorResponse(BaseModel):
    """Standardized error response"""
    status: bool = Field(False, description="Request success status")
    resultData: dict = Field(..., description="Error details")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": False,
                "resultData": {
                    "error": "Error message",
                    "detail": "Detailed error information"
                }
            }
        }


def success_response(data: Any) -> dict:
    """
    Create a success response in standardized format.
    
    Args:
        data: The data to return
        
    Returns:
        Dict with status=True and resultData containing the data
    """
    return {
        "status": True,
        "resultData": data
    }


def error_response(error: str, detail: Optional[str] = None) -> dict:
    """
    Create an error response in standardized format.
    
    Args:
        error: Error message
        detail: Optional detailed error information
        
    Returns:
        Dict with status=False and resultData containing error info
    """
    result_data = {"error": error}
    if detail:
        result_data["detail"] = detail
    
    return {
        "status": False,
        "resultData": result_data
    }
