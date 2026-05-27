import httpx
import secrets
import os
import redis.asyncio as redis
from typing import Dict, Any
from dotenv import load_dotenv

# 🚀 FORCE PYTHON TO LOAD THE .ENV FILE IMMEDIATELY
load_dotenv()

class ARKAOrchestrator:
    def __init__(self):
        # 1. Persistent Storage (Supabase)
        self.supabase_url = os.getenv("SUPABASE_URL", "")
        self.supabase_key = os.getenv("SUPABASE_KEY", "")
        self.table_name = "request_logs"
        self.waitlist_table = "waitlist"
        
        # 2. High-Velocity Gateway Cache & Ledger (Redis)
        # Using decode_responses=True so we get strings, not byte-strings
        self.redis = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
        
        self.providers = {
            "groq": {
                "base_url": "https://api.groq.com/openai/v1/chat/completions",
                "key": os.getenv("GROQ_API_KEY", "")
            },
            "openrouter": {
                "base_url": "https://openrouter.ai/api/v1/chat/completions",
                "key": os.getenv("OPENROUTER_API_KEY", "")
            },
            "deepseek": {
                "base_url": "https://api.deepseek.com/chat/completions",
                "key": os.getenv("DEEPSEEK_API_KEY", "")
            },
            "gemini": {
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                "key": os.getenv("GEMINI_API_KEY", "")
            }
        }

    async def generate_api_key(self):
        """Provisions key to Supabase (Permanent) AND Redis (High-Speed Cache)"""
        raw_key = secrets.token_urlsafe(32)
        arka_key = f"arka_live_{raw_key}"
        
        if self.supabase_url and self.supabase_key:
            async with httpx.AsyncClient() as client:
                try:
                    # 1. Save to Supabase (Permanent Record)
                    response = await client.post(
                        f"{self.supabase_url}/rest/v1/api_keys",
                        headers={
                            "apikey": self.supabase_key,
                            "Authorization": f"Bearer {self.supabase_key}",
                            "Content-Type": "application/json",
                            "Prefer": "return=minimal"
                        },
                        json={
                            "key_value": arka_key,
                            "key_name": "My Default ARKA Key",
                            "is_active": True,
                            "tier": "Hobby",
                            "request_count": 0
                        }
                    )
                    response.raise_for_status() 
                    
                    # 2. Initialize high-speed state in Redis via Pipeline
                    async with self.redis.pipeline(transaction=True) as pipe:
                        pipe.hset(f"api_key:{arka_key}", mapping={
                            "status": "active",
                            "tier": "Hobby"
                        })
                        # Initialize wallet with a $1.00 testing credit
                        pipe.hset(f"wallet:{arka_key}", "balance", "1.00")
                        await pipe.execute()
                        
                except Exception as e:
                    print(f"Key Provisioning Error: {e}")
                    return {"error": "Infrastructure sync failed"}
                    
        return {"api_key": arka_key, "message": "Key generated. Wallet funded with $1.00 test credit."}
    
    async def gateway_security_check(self, api_key: str) -> dict:
        """Phase 1 Guard: Instant Identity, Ledger, and Rate Limit verification."""
        
        # 1. Identity Check
        key_status = await self.redis.hget(f"api_key:{api_key}", "status")
        if not key_status or key_status != "active":
            return {"authorized": False, "status_code": 401, "detail": "Invalid or revoked ARKA Key."}

        # 2. Financial Circuit Breaker
        balance = await self.redis.hget(f"wallet:{api_key}", "balance")
        if balance is None or float(balance) <= 0.0001:
            return {"authorized": False, "status_code": 402, "detail": "Payment Required. Wallet depleted."}

        # 3. Token-Aware Throttling (60 requests per minute ceiling)
        rate_key = f"rate_limit:{api_key}"
        requests = await self.redis.incr(rate_key)
        if requests == 1:
            await self.redis.expire(rate_key, 60)
        
        if requests > 60:
            return {"authorized": False, "status_code": 429, "detail": "Compute throttling active."}

        return {"authorized": True, "api_key": api_key, "current_balance": float(balance)}

    async def log_request(self, api_key: str, model: str, prompt_tokens: int, completion_tokens: int, cost: float, tenant_id: str):
        """Saves the log PERMANENTLY to Supabase."""
        log_entry = {
            "api_key_id": 1, 
            "model_used": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_cost": cost,
            "tenant_id": tenant_id
        }

        if self.supabase_url and self.supabase_key:
            async with httpx.AsyncClient() as client:
                try:
                    await client.post(
                        f"{self.supabase_url}/rest/v1/{self.table_name}",
                        headers={
                            "apikey": self.supabase_key,
                            "Authorization": f"Bearer {self.supabase_key}",
                            "Content-Type": "application/json",
                            "Prefer": "return=minimal"
                        },
                        json=log_entry
                    )
                except Exception as e:
                    print(f"Supabase Cloud Sync Error: {e}")

    def _determine_provider(self, model: str) -> str:
        if "llama" in model.lower() or "mixtral" in model.lower():
            return "groq"
        elif "deepseek" in model.lower():
            return "deepseek"
        elif "gemini" in model.lower():
            return "gemini"
        else:
            return "openrouter"

    async def route_request(self, api_key: str, prompt: str, requested_model: str = "llama-3.1-8b-instant", tenant_id: str = "anonymous"):
        # --- PHASE 1 GATEWAY CHECK ---
        security = await self.gateway_security_check(api_key)
        if not security["authorized"]:
            return {"error": security["detail"]}

        provider_name = self._determine_provider(requested_model)
        provider_config = self.providers.get(provider_name)

        if not provider_config or not provider_config["key"]:
            return {"error": f"Server missing API Key for provider: {provider_name}"}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    provider_config["base_url"],
                    headers={
                        "Authorization": f"Bearer {provider_config['key']}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": requested_model,
                        "messages": [{"role": "user", "content": prompt}]
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                ai_data = response.json()
            except Exception as e:
                return {"error": f"Upstream provider ({provider_name}) failed: {str(e)}"}

        # Calculate exact micro-transaction cost
        usage = ai_data.get("usage", {})
        p_tokens = usage.get("prompt_tokens", 0)
        c_tokens = usage.get("completion_tokens", 0)
        simulated_retail_cost = (p_tokens * 0.000001) + (c_tokens * 0.000002)

        # --- FINANCIAL LEDGER DEDUCTION ---
        new_balance = await self.redis.hincrbyfloat(f"wallet:{api_key}", "balance", -simulated_retail_cost)
        
        await self.log_request(api_key, requested_model, p_tokens, c_tokens, simulated_retail_cost, tenant_id)
        
        return {
            "answer": ai_data["choices"][0]["message"]["content"],
            "model_used": requested_model,
            "provider": provider_name,
            "tokens": usage,
            "cost_deducted": simulated_retail_cost,
            "wallet_balance_remaining": new_balance
        }

    async def fetch_logs(self):
        """Fetches telemetry logs from Supabase."""
        if self.supabase_url and self.supabase_key:
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(
                        f"{self.supabase_url}/rest/v1/{self.table_name}?select=*&order=created_at.desc&limit=50",
                        headers={
                            "apikey": self.supabase_key,
                            "Authorization": f"Bearer {self.supabase_key}"
                        }
                    )
                    return response.json()
                except Exception as e:
                    print(f"Fetch Logs Error: {e}")
        return []

    async def join_waitlist(self, email: str, tier: str):
        """Adds user to waitlist in Supabase."""
        if self.supabase_url and self.supabase_key:
            async with httpx.AsyncClient() as client:
                try:
                    await client.post(
                        f"{self.supabase_url}/rest/v1/{self.waitlist_table}",
                        headers={
                            "apikey": self.supabase_key,
                            "Authorization": f"Bearer {self.supabase_key}",
                            "Content-Type": "application/json",
                            "Prefer": "return=minimal"
                        },
                        json={"email": email, "tier": tier}
                    )
                    return {"status": "success"}
                except Exception as e:
                    return {"error": str(e)}
        return {"error": "Supabase not configured"}

arka_engine = ARKAOrchestrator()