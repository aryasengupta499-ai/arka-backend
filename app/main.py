from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.proxy import router as proxy_router, limiter
# from app.core.config import settings # (Assuming this is handled, otherwise comment out)
from app.services.orchestrator import arka_engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP: Fire up and test the Redis connection before accepting traffic
    try:
        await arka_engine.redis.ping()
        print("🚀 ARKA Engine: Redis Cache Connected successfully!")
    except Exception as e:
        print(f"❌ ARKA Engine: CRITICAL REDIS ERROR: {e}")
        print("Check your Upstash URL in the .env file.")
    
    yield  # The app runs and accepts traffic here
    
    # SHUTDOWN: Cleanly sever the Redis connection so we don't leak memory
    await arka_engine.redis.close()
    print("🛑 ARKA Engine: Redis Cache Disconnected cleanly.")

# Inject the lifespan into the FastAPI app
app = FastAPI(title="ARKA Gateway", lifespan=lifespan)

# --- RATE LIMITER SETUP ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- GLOBAL CORS ALLOWANCE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Opens the door completely for frontend testing
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

app.include_router(proxy_router, prefix="", tags=["Proxy"])

@app.get("/")
async def root():
    return {
        "message": "ARKA Financial API Gateway is Online", 
        "version": "2.1.0-Redis-Ledger",
        "status": "Operational",
        "protection": "SlowAPI + Redis Token Throttling Active"
    }