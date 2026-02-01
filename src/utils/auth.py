"""
JWT Authentication utilities and dependencies.
Validates JWT tokens from external authentication service.
"""
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from src.config.settings import Settings

# Initialize settings
settings = Settings()

# HTTP Bearer security scheme
security = HTTPBearer()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> UUID:
    """
    Dependency to extract and validate user_id from JWT token.
    
    Args:
        credentials: HTTP Authorization credentials with Bearer token
        
    Returns:
        UUID of the authenticated user
        
    Raises:
        HTTPException: If token is invalid or user_id cannot be extracted
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id_str: str = payload.get("user_id")
        
        if user_id_str is None:
            raise credentials_exception
            
        # Convert string UUID to UUID object
        user_id = UUID(user_id_str)
        
    except JWTError:
        raise credentials_exception
    except ValueError:
        raise credentials_exception
        
    return user_id