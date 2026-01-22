from fastapi import HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import os

# กำหนด SECRET_KEY (ควรเก็บใน .env)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"

security = HTTPBearer()

async def verify_jwt(credentials: HTTPAuthorizationCredentials) -> dict:
    """
    ตรวจสอบ JWT token และ return ข้อมูลใน token
    """
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Print ข้อมูลใน token
        print("=== JWT Token Information ===")
        print(f"User ID: {payload.get('user_id')}")
        print(f"Email: {payload.get('email')}")
        print(f"Role: {payload.get('role')}")
        print(f"Expired at: {payload.get('exp')}")
        print(f"All payload: {payload}")
        print("============================")
        
        return payload
    
    except JWTError as e:
        print(f"JWT Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_current_user(payload: dict) -> dict:
    """
    ดึงข้อมูล user จาก JWT payload
    """
    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    return payload
