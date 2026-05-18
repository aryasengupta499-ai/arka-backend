from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.api.v1.proxy import router as proxy_router, limiter
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)

# --- RATE LIMITER SETUP ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- GLOBAL CORS ALLOWANCE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Opens the door completely for testing your deployment
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

app.include_router(proxy_router, prefix="", tags=["Proxy"])

@app.get("/")
async def root():
    return {
        "message": "ARKA Engine is Online", 
        "version": "2.0.0-Best",
        "status": "Operational",
        "protection": "slowapi rate-limiting active"
    }