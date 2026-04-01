"""
DTOs for LLM utility endpoints (e.g. suggest relation between entities).
"""
from enum import Enum
from pydantic import BaseModel, Field
from uuid import UUID


class RelationEntityType(str, Enum):
    """Entity kind for polymorphic suggest-relation sides."""

    NODE = "node"
    WORKSPACE = "workspace"
    FILE = "file"


class SuggestRelationRequest(BaseModel):
    """Suggest how parent relates to child; content for each side is loaded by type."""

    parent_id: UUID = Field(..., description="UUID of the parent side (see type_of_parent)")
    child_id: UUID = Field(..., description="UUID of the child side (see type_of_child)")
    type_of_parent: RelationEntityType = Field(
        ...,
        description="Where to load parent text from: node, workspace, or file (metadata only for file)",
    )
    type_of_child: RelationEntityType = Field(
        ...,
        description="Where to load child text from: node, workspace, or file (metadata only for file)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "parent_id": "550e8400-e29b-41d4-a716-446655440001",
                "child_id": "550e8400-e29b-41d4-a716-446655440002",
                "type_of_parent": "workspace",
                "type_of_child": "node",
            }
        }


class SuggestRelationItem(BaseModel):
    """One suggested relation between two contents (relation_type_id must exist in RelationTypes)."""
    relation_type_id: str = Field(..., description="Chosen relation type id from database RelationTypes")
    explanation: str = Field(..., description="Short explanation of the relation")

    class Config:
        json_schema_extra = {
            "example": {
                "relation_type_id": "PART",
                "explanation": "The workspace organizes the node as part of its structure.",
            }
        }


class SuggestRelationResponse(BaseModel):
    """Response with exactly one LLM-chosen relation from RelationTypes."""
    suggestion: SuggestRelationItem = Field(
        ...,
        description="Single best-matching relation type from the database for parent to child",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "suggestion": {
                    "relation_type_id": "PART",
                    "explanation": "The workspace organizes the node as part of its structure.",
                }
            }
        }
