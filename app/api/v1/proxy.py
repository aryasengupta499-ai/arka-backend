from fastapi import APIRouter, HTTPException, Depends, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.services.orchestrator import arka_engine

# Initialize the rate limiter using the client's IP address
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()
security = HTTPBearer()

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    prompt: Optional[str] = None
    messages: Optional[List[Message]] = None
    model: str = "llama-3.1-8b-instant" 

class WaitlistRequest(BaseModel):
    email: str
    tier: str

@router.post("/generate-key")
@limiter.limit("5/minute") # Protects against spam key generation
async def create_api_key(request: Request):
    """Endpoint for the frontend 'Generate API Key' button"""
    result = await arka_engine.generate_api_key()
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result

@router.post("/chat")
@limiter.limit("60/minute") # Protects the proxy endpoint from DDoS
async def process_chat(request: Request, chat_payload: ChatRequest, creds: HTTPAuthorizationCredentials = Security(security)):
    """The locked AI proxy route. Requires a valid ARKA Bearer Token."""
    api_key = creds.credentials
    
    # NEW: Extract the tenant ID from headers (default to 'anonymous' if missing)
    tenant_id = request.headers.get("x-arka-tenant-id", "anonymous")
    
    # 1. The Bouncer: Extract the full key record (including tier and request_count)
    key_record = await arka_engine.validate_api_key(api_key)
    if not key_record:
        raise HTTPException(status_code=401, detail="Invalid or unauthorized ARKA API Key")

    # 2. Extract incoming text payload safely
    extracted_text = chat_payload.prompt
    if chat_payload.messages and len(chat_payload.messages) > 0:
        extracted_text = chat_payload.messages[-1].content

    if not extracted_text:
        raise HTTPException(status_code=400, detail="No prompt or messages provided in payload")

    # 3. Route downward passing the ENTIRE key record and the NEW tenant_id
    result = await arka_engine.route_request(
        key_record=key_record,
        prompt=extracted_text, 
        requested_model=chat_payload.model,
        tenant_id=tenant_id
    )

    if "error" in result:
        raise HTTPException(status_code=402, detail=result["error"]) # 402 Payment Required!

    return result

@router.get("/logs")
async def get_telemetry_logs():
    """Fetches the FinOps ledger from Supabase for the dashboard"""
    return await arka_engine.fetch_logs()

@router.post("/waitlist")
@limiter.limit("10/minute") # Protects your waitlist database from spam
async def join_waitlist(request: Request, waitlist_payload: WaitlistRequest):
    """Saves email leads securely to Supabase"""
    result = await arka_engine.join_waitlist(waitlist_payload.email, waitlist_payload.tier)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return {"message": "Successfully joined the waitlist"}