from fastapi import FastAPI, Depends, status
from fastapi.security import HTTPAuthorizationCredentials
from api import embedding
from middleware.auth import verify_jwt, security, get_current_user
from dotenv import load_dotenv
import uvicorn

# Load environment variables
load_dotenv()

app = FastAPI()

@app.get("/", status_code=status.HTTP_200_OK)
async def root():
    return {"message": "Dimension API Brain"}

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "ok"}

# Public route - no JWT required
@app.get("/public")
async def public_route():
    return {"message": "This is a public route"}

# Protected route - JWT required
@app.post("/embedding/create", status_code=status.HTTP_201_CREATED)
async def create_embedding(
    node_id: str, 
    user_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    # ตรวจสอบ JWT
    payload = await verify_jwt(credentials)
    current_user = get_current_user(payload)
    
    # เรียกใช้ embedding
    result = await embedding.Create(node_id, user_id)
    
    return {
        "user_info": {
            "user_id": current_user.get("user_id"),
            "email": current_user.get("email"),
            "role": current_user.get("role")
        },
        "result": result
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)