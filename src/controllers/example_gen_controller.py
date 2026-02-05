"""
Example Generation Controller.
Endpoint for generating sample data using AI.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from src.database import get_db
from src.services.example_gen_service import ExampleGenService
from src.dto.example_gen_dto import ExampleGenRequest, ExampleGenResponse
from src.dto.response_dto import success_response, error_response
from src.utils.auth import get_current_user_id

router = APIRouter(
    prefix="/examplegen",
    tags=["Example Generation"]
)


@router.post(
    "",
    status_code=status.HTTP_200_OK,
    summary="Generate example data",
    description="Use AI to generate sample data for a database table based on a prompt"
)
async def generate_examples(
    request: ExampleGenRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    Generate example data using OpenAI.
    
    The AI agent will:
    1. Analyze the table schema from the database
    2. Think about what data to generate based on the prompt
    3. Create realistic sample data matching the schema
    4. Generate an INSERT query for the data
    5. Optionally execute the INSERT (if execute_insert=true)
    
    Safety Features:
    - Only INSERT queries are allowed
    - Blocks DELETE, DROP, TRUNCATE, UPDATE, and other dangerous operations
    - Validates query before execution
    - Automatic rollback on errors
    
    Requires JWT authentication.
    """
    try:
        service = ExampleGenService(db)
        result = service.generate_examples(
            table_name=request.table_name,
            prompt=request.prompt,
            user_id=user_id,
            execute_insert=request.execute_insert
        )
        
        response = ExampleGenResponse(**result)
        
        if response.success:
            return success_response(response.model_dump())
        else:
            return error_response(
                message=response.error or "Failed to generate examples",
                details={"raw_response": response.raw_response}
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating examples: {str(e)}"
        )
