"""
DTOs for LLM utility endpoints (e.g. suggest relation between nodes).
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID


class SuggestRelationRequest(BaseModel):
    """Request body for suggesting relations between two nodes."""
    node_a: UUID = Field(..., description="First node UUID")
    node_b: UUID = Field(..., description="Second node UUID")

    class Config:
        json_schema_extra = {
            "example": {
                "node_a": "550e8400-e29b-41d4-a716-446655440001",
                "node_b": "550e8400-e29b-41d4-a716-446655440002"
            }
        }


class SuggestRelationItem(BaseModel):
    """One suggested relation between two contents."""
    relation_type_id: str = Field(..., description="Suggested relation type identifier")
    explanation: str = Field(..., description="Short explanation of the relation")

    class Config:
        json_schema_extra = {
            "example": {
                "relation_type_id": "RELATED",
                "explanation": "Both nodes discuss the same topic from different angles."
            }
        }


class SuggestRelationResponse(BaseModel):
    """Response with 3-5 relation suggestions for the user to choose from."""
    suggestions: List[SuggestRelationItem] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="List of 3 to 5 suggested relations"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "suggestions": [
                    {"relation_type_id": "RELATED", "explanation": "Both cover the same theme."},
                    {"relation_type_id": "CONTAINS", "explanation": "Node A contains details expanded in Node B."},
                    {"relation_type_id": "DEPENDS_ON", "explanation": "Node B builds on concepts in Node A."}
                ]
            }
        }
