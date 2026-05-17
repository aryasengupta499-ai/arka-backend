from fastapi import APIRouter, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional
from app.services.orchestrator import arka_engine

router = APIRouter()
security = HTTPBearer()

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    prompt: Optional[str] = None
    messages: Optional[List[Message]] = None
    model: str = "llama-3.1-8b-instant" 

# Added the Waitlist data model
class WaitlistRequest(BaseModel):
    email: str
    tier: str

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
    api_key = creds.credentials
    
    # 1. The Bouncer: Extract key record data out of validation lookup
    key_record = await arka_engine.validate_api_key(api_key)
    if not key_record:
        raise HTTPException(status_code=401, detail="Invalid or unauthorized ARKA API Key")

    # 2. Extract incoming text payload safely
    extracted_text = request.prompt
    if request.messages and len(request.messages) > 0:
        extracted_text = request.messages[-1].content

    if not extracted_text:
        raise HTTPException(status_code=400, detail="No prompt or messages provided in payload")

    user_id = "test_developer"
    
    # 3. Route downward passing the key_record ID along
    result = await arka_engine.route_request(
        api_key_id=key_record["id"],
        user_id=user_id,
        prompt=extracted_text, 
        requested_model=request.model
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result

@router.get("/logs")
async def get_telemetry_logs():
    """Fetches the FinOps ledger from Supabase for the dashboard"""
    return await arka_engine.fetch_logs()

# Added the new Waitlist Endpoint
@router.post("/waitlist")
async def join_waitlist(request: WaitlistRequest):
    """Saves email leads securely to Supabase"""
    result = await arka_engine.join_waitlist(request.email, request.tier)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return {"message": "Successfully joined the waitlist"}