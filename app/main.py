from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.proxy import router as proxy_router
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)

# --- THE VIP LIST ---
# This acts as the final shield. Only these URLs can talk to your backend.
origins = [
    "http://localhost:3000",       # For when you test the UI on your laptop
    "http://127.0.0.1:3000",       # Alternate local React port
    "https://your-vercel-app-url.vercel.app" # <--- REPLACE WITH YOUR EXACT VERCEL LINK
]

# --- ADD CORS MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Locked down to only the VIP list!
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

# Only loading the Proxy router
app.include_router(proxy_router, prefix=settings.API_V1_STR, tags=["Proxy"])

@app.get("/")
async def root():
    return {
        "message": "ARKA Engine is Online", 
        "version": "2.0.0-Best",
        "status": "Operational"
    }