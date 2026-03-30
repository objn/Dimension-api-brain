"""
DTOs for LLM utility endpoints (e.g. suggest relation between nodes).
"""
from pydantic import BaseModel, Field
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
    """One suggested relation between two contents (relation_type_id must exist in RelationTypes)."""
    relation_type_id: str = Field(..., description="Chosen relation type id from database RelationTypes")
    explanation: str = Field(..., description="Short explanation of the relation")

    class Config:
        json_schema_extra = {
            "example": {
                "relation_type_id": "CONTAINS",
                "explanation": "Node A contains details expanded in Node B."
            }
        }


class SuggestRelationResponse(BaseModel):
    """Response with exactly one LLM-chosen relation from RelationTypes."""
    suggestion: SuggestRelationItem = Field(
        ...,
        description="Single best-matching relation type from the database for the two nodes",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "suggestion": {
                    "relation_type_id": "CONTAINS",
                    "explanation": "Node A contains details expanded in Node B.",
                }
            }
        }
