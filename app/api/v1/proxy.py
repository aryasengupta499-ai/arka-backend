from fastapi import APIRouter, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from app.services.orchestrator import arka_engine

router = APIRouter()

# This activates the little "Padlock" icon in your Swagger UI!
security = HTTPBearer()

class ChatRequest(BaseModel):
    prompt: str
    model: str = "llama-3.1-8b-instant" 

@router.post("/generate-key")
async def create_api_key():
    """Endpoint for the frontend 'Generate API Key' button"""
    result = await arka_engine.generate_api_key()
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result

@router.post("/chat")
async def process_chat(request: ChatRequest, creds: HTTPAuthorizationCredentials = Security(security)):
    """The locked AI proxy route. Requires a valid ARKA Bearer Token."""
    
    # 1. The Bouncer: Check the key
    api_key = creds.credentials
    is_valid = await arka_engine.validate_api_key(api_key)
    
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid or unauthorized ARKA API Key")

    # 2. If the key is valid, proceed with the intercept
    user_id = "test_developer"

    result = await arka_engine.route_request(
        user_id=user_id,
        prompt=request.prompt,
        requested_model=request.model
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result

@router.get("/logs")
async def get_telemetry_logs():
    """Fetches the FinOps ledger from Supabase for the dashboard"""
    return await arka_engine.fetch_logs()