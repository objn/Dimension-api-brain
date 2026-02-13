"""
Example Generation Service.
Uses OpenAI to generate sample data based on table name and prompt.
"""
from typing import Dict, Any, List
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import text
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import httpx
import json
import uuid as uuid_lib

from src.config.settings import settings
from src.database import get_db


class ExampleGenService:
    """Service for generating sample data using OpenAI"""
    
    def __init__(self, db: Session):
        self.db = db
        self.llm = self._get_llm()
    
    def _get_llm(self) -> ChatOpenAI:
        """Initialize OpenAI LLM"""
        http_client = httpx.Client(
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=60.0
        )
        return ChatOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            temperature=0.7,
            http_client=http_client
        )
    
    def generate_examples(
        self,
        table_name: str,
        prompt: str,
        user_id: UUID,
        execute_insert: bool = False
    ) -> Dict[str, Any]:
        """
        Generate sample data for a table based on prompt.
        
        Args:
            table_name: Name of the database table
            prompt: User prompt describing the data to generate
            user_id: ID of the user making the request
            execute_insert: Whether to execute the INSERT query (safety: only INSERT allowed)
            
        Returns:
            Dictionary containing generated data and query
        """
        
        # Get table schema
        table_schema = self._get_table_schema(table_name)
        
        # Create system prompt for the AI
        system_prompt = f"""You are an expert database data generator.
Your task is to generate realistic sample data for database tables based on user requirements.

Table Schema:
{table_schema}

Current User ID (for audit fields): {user_id}

Instructions:
1. Analyze the table schema and user prompt carefully
2. Generate appropriate sample data that matches the schema
3. Return a valid JSON response with the following structure:
{{
    "thought_process": "Your reasoning about what data to generate",
    "generated_data": [
        // Array of data objects matching the table schema
        // DO NOT include created_at, created_by, updated_at, updated_by in this array
        // Include ALL other columns from the schema
    ],
    "record_count": number of records generated
}}

Important:
- Use appropriate data types matching the schema
- Generate realistic and diverse data
- Include all required fields EXCEPT audit fields (created_at, created_by, updated_at, updated_by)
- Use UUIDs for UUID fields (generate new ones for primary keys)
- Ensure foreign keys reference valid data if applicable
- For text/markdown content with newlines, use actual newlines in the JSON string (not \\n escape sequences)
- The INSERT query will be built automatically from your generated_data - DO NOT include an insert_query field
"""
        
        # Invoke LLM
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Table: {table_name}\n\nRequirement: {prompt}")
        ]
        
        response = self.llm.invoke(messages)
        
        # Parse response
        try:
            # Try to extract JSON from response
            content = response.content.strip()
            
            # Remove markdown code blocks if present
            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "").strip()
            elif content.startswith("```"):
                content = content.replace("```", "").strip()
            
            result = json.loads(content)
            
            generated_data = result.get("generated_data", [])
            
            # Build INSERT query programmatically
            insert_query = self._build_insert_query(
                table_name=table_name,
                data=generated_data,
                user_id=user_id
            )
            
            response_data = {
                "success": True,
                "table_name": table_name,
                "thought_process": result.get("thought_process", ""),
                "generated_data": generated_data,
                "insert_query": insert_query,
                "record_count": result.get("record_count", len(generated_data)),
                "executed": False,
                "inserted_records": 0,
                "raw_response": content
            }
            
            # Execute INSERT if requested
            if execute_insert and insert_query:
                execution_result = self._safe_execute_insert(insert_query)
                response_data["executed"] = execution_result["success"]
                response_data["inserted_records"] = execution_result.get("inserted_records", 0)
                if not execution_result["success"]:
                    response_data["error"] = execution_result.get("error", "")
            
            return response_data
            
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Failed to parse LLM response: {str(e)}",
                "raw_response": response.content
            }
    
    def _get_table_schema(self, table_name: str) -> str:
        """
        Get table schema from database.
        
        Args:
            table_name: Name of the table
            
        Returns:
            String representation of table schema
        """
        try:
            # Query to get table structure from PostgreSQL
            query = text("""
                SELECT 
                    column_name,
                    data_type,
                    is_nullable,
                    column_default,
                    character_maximum_length
                FROM information_schema.columns
                WHERE table_name = :table_name
                ORDER BY ordinal_position;
            """)
            
            result = self.db.execute(query, {"table_name": table_name})
            columns = result.fetchall()
            
            if not columns:
                return f"Table '{table_name}' not found or has no columns"
            
            # Format schema as readable text
            schema_lines = [f"Table: {table_name}", "Columns:"]
            for col in columns:
                col_name, data_type, nullable, default, max_length = col
                nullable_str = "NULL" if nullable == "YES" else "NOT NULL"
                default_str = f", DEFAULT: {default}" if default else ""
                length_str = f"({max_length})" if max_length else ""
                
                schema_lines.append(
                    f"  - {col_name}: {data_type}{length_str} {nullable_str}{default_str}"
                )
            
            return "\n".join(schema_lines)
            
        except Exception as e:
            return f"Error fetching schema for table '{table_name}': {str(e)}"
    
    def _build_insert_query(
        self,
        table_name: str,
        data: List[Dict[str, Any]],
        user_id: UUID
    ) -> str:
        """
        Build a proper PostgreSQL INSERT query with correct quoting.
        
        Args:
            table_name: Name of the table
            data: List of data dictionaries to insert
            user_id: User ID for audit fields
            
        Returns:
            Properly formatted INSERT query string
        """
        if not data:
            return ""
        
        # Get all columns from the first data record
        data_columns = list(data[0].keys())
        
        # Add audit columns
        audit_columns = ["created_at", "created_by", "updated_at", "updated_by"]
        all_columns = data_columns + audit_columns
        
        # Build column list with proper quoting
        quoted_columns = [f'"{col}"' for col in all_columns]
        columns_str = ", ".join(quoted_columns)
        
        # Build VALUES clauses for each record
        values_clauses = []
        for record in data:
            values = []
            for col in data_columns:
                value = record.get(col)
                values.append(self._format_sql_value(value))
            
            # Add audit field values
            values.append("NOW()")  # created_at
            values.append(f"'{user_id}'")  # created_by
            values.append("NOW()")  # updated_at
            values.append(f"'{user_id}'")  # updated_by
            
            values_clauses.append(f"({', '.join(values)})")
        
        # Combine into final INSERT statement
        values_str = ",\n".join(values_clauses)
        
        return f'INSERT INTO "{table_name}" ({columns_str}) VALUES\n{values_str};'
    
    def _format_sql_value(self, value: Any) -> str:
        """
        Format a Python value as a PostgreSQL SQL literal.
        
        Args:
            value: The value to format
            
        Returns:
            SQL literal string
        """
        if value is None:
            return "NULL"
        
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        
        if isinstance(value, (int, float)):
            return str(value)
        
        if isinstance(value, str):
            # Convert escaped newlines to actual newlines
            # LLM might return \\n in JSON which becomes \n literal string after parsing
            value = value.replace("\\n", "\n")
            value = value.replace("\\t", "\t")
            
            # Use dollar quoting for strings that might contain special characters
            # This avoids issues with single quotes and backslashes
            if "'" in value or "\\" in value or "\n" in value or "$" in value:
                # Find a unique dollar quote tag that doesn't appear in the value
                tag = "content"
                counter = 0
                while f"${tag}$" in value:
                    tag = f"content{counter}"
                    counter += 1
                return f"${tag}${value}${tag}$"
            else:
                # Simple string - use single quotes
                return f"'{value}'"
        
        if isinstance(value, list):
            # PostgreSQL array
            formatted_items = [self._format_sql_value(item) for item in value]
            return f"ARRAY[{', '.join(formatted_items)}]"
        
        if isinstance(value, dict):
            # JSON/JSONB
            json_str = json.dumps(value)
            return f"'{json_str}'::jsonb"
        
        # Default: treat as string
        return f"'{str(value)}'"
    
    def _safe_execute_insert(self, insert_query: str) -> Dict[str, Any]:
        """
        Safely execute INSERT query with validation.
        Only INSERT queries are allowed - prevents DELETE, DROP, TRUNCATE, etc.
        
        Args:
            insert_query: The SQL query to execute
            
        Returns:
            Dictionary with execution result
        """
        try:
            # Normalize query for validation
            query_upper = insert_query.strip().upper()
            
            # Security check: Only allow INSERT statements
            if not query_upper.startswith("INSERT"):
                return {
                    "success": False,
                    "error": "Only INSERT queries are allowed. DELETE, DROP, TRUNCATE and other operations are blocked for safety."
                }
            
            # Additional safety checks - block dangerous statement beginnings
            # We check for patterns that indicate a separate dangerous statement
            # Not just keywords that might appear in data or column names
            import re
            dangerous_patterns = [
                r';\s*DELETE\b',
                r';\s*DROP\b',
                r';\s*TRUNCATE\b',
                r';\s*ALTER\b',
                r';\s*UPDATE\b',
                r';\s*GRANT\b',
                r';\s*REVOKE\b',
                r';\s*CREATE\b',
                r';\s*REPLACE\b',
                r';\s*EXECUTE\b',
                r';\s*CALL\b',
                r';\s*MERGE\b',
            ]
            
            for pattern in dangerous_patterns:
                if re.search(pattern, query_upper):
                    keyword = pattern.split(r'\b')[0].replace(r';\s*', '').strip('\\')
                    return {
                        "success": False,
                        "error": f"Query contains dangerous statement. Only single INSERT operations are allowed for safety."
                    }
            
            # Execute the INSERT query
            result = self.db.execute(text(insert_query))
            self.db.commit()
            
            # Get number of inserted records
            inserted_count = result.rowcount if hasattr(result, 'rowcount') else 0
            
            return {
                "success": True,
                "inserted_records": inserted_count
            }
            
        except Exception as e:
            # Rollback on error
            self.db.rollback()
            return {
                "success": False,
                "error": f"Failed to execute INSERT query: {str(e)}",
                "inserted_records": 0
            }
