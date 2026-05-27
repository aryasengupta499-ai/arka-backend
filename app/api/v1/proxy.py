import os
import stripe
from fastapi import APIRouter, HTTPException, Depends, Security, Request, Header
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

# Initialize Stripe for Phase 2: Automated Machine Billing
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

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
@limiter.limit("5/minute")
async def create_api_key(request: Request):
    """Provisions key to Supabase AND spins up the live Redis Wallet."""
    result = await arka_engine.generate_api_key()
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result

@router.post("/chat")
@limiter.limit("60/minute") 
async def process_chat(request: Request, chat_payload: ChatRequest, creds: HTTPAuthorizationCredentials = Security(security)):
    """The locked AI proxy route. Guarded by the ultra-fast Redis Ledger."""
    api_key = creds.credentials
    tenant_id = request.headers.get("x-arka-tenant-id", "anonymous")
    
    extracted_text = chat_payload.prompt
    if chat_payload.messages and len(chat_payload.messages) > 0:
        extracted_text = chat_payload.messages[-1].content

    if not extracted_text:
        raise HTTPException(status_code=400, detail="No prompt or messages provided in payload")

    # 🚀 THE HANDOFF: Orchestrator's Redis engine does the heavy lifting.
    result = await arka_engine.route_request(
        api_key=api_key,
        prompt=extracted_text, 
        requested_model=chat_payload.model,
        tenant_id=tenant_id
    )

    if "error" in result:
        error_msg = result["error"]
        if "Payment Required" in error_msg:
            raise HTTPException(status_code=402, detail=error_msg)
        elif "throttling" in error_msg.lower() or "limit" in error_msg.lower():
            raise HTTPException(status_code=429, detail=error_msg)
        elif "Invalid" in error_msg or "revoked" in error_msg:
            raise HTTPException(status_code=401, detail=error_msg)
        else:
            raise HTTPException(status_code=400, detail=error_msg)

    return result

@router.get("/logs")
async def get_telemetry_logs():
    """Fetches the FinOps ledger from Supabase for the dashboard"""
    return await arka_engine.fetch_logs()

@router.post("/waitlist")
@limiter.limit("10/minute") 
async def join_waitlist(request: Request, waitlist_payload: WaitlistRequest):
    result = await arka_engine.join_waitlist(waitlist_payload.email, waitlist_payload.tier)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return {"message": "Successfully joined the waitlist"}

# ==========================================
# PHASE 2: STRIPE AUTOMATED BILLING WEBHOOK
# ==========================================

@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    """
    Listens for sandbox transaction settlements. When an agent pays,
    this instantly bumps their Redis wallet balance so they can resume compute.
    """
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Stripe payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        api_key = session.get('client_reference_id') 
        amount_paid = session.get('amount_total', 0) / 100.0  # Convert cents to dollars

        if api_key:
            new_balance = await arka_engine.redis.hincrbyfloat(f"wallet:{api_key}", "balance", amount_paid)
            print(f"💰 STRIPE RECHARGE: Added ${amount_paid} to {api_key}. New Balance: ${new_balance}")
            
    return {"status": "success"}