from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.proxy import router as proxy_router
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)

# --- GLOBAL CORS ALLOWANCE ---
# This guarantees that your Vercel frontend can bypass all browser security checks
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Opens the door completely for testing your deployment
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

# --- REMOVED THE PREFIX ---
# Now your endpoints live at /logs, /chat, and /generate-key perfectly matching your UI
app.include_router(proxy_router, prefix="", tags=["Proxy"])

@app.get("/")
async def root():
    return {
        "message": "ARKA Engine is Online", 
        "version": "2.0.0-Best",
        "status": "Operational"
    }