import httpx
import secrets
import os
from typing import Dict, Any

class ARKAOrchestrator:
    def __init__(self):
        self.spend_caps = {"default": 10.00}
        self.current_spend = 0.00
        
        # Pull Supabase keys for direct REST API access
        self.supabase_url = os.getenv("SUPABASE_URL", "")
        self.supabase_key = os.getenv("SUPABASE_KEY", "")
        
        # Mapped perfectly to your live database setup
        self.table_name = "request_logs"
        
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
        """Generates a secure ARKA API key and saves it to your existing schema"""
        raw_key = secrets.token_urlsafe(32)
        arka_key = f"arka_live_{raw_key}"
        
        if self.supabase_url and self.supabase_key:
            async with httpx.AsyncClient() as client:
                try:
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
                            "is_active": True
                        }
                    )
                    response.raise_for_status() 
                except Exception as e:
                    print(f"Supabase Key Save Error: {e}")
                    return {"error": "Database sync failed"}
                    
        return {"api_key": arka_key}
    
    async def validate_api_key(self, api_key: str) -> Any:
        """The Bouncer: Checks if the API key exists and returns its complete row dictionary"""
        if not self.supabase_url or not self.supabase_key:
            return None 

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.supabase_url}/rest/v1/api_keys?key_value=eq.{api_key}&is_active=eq.true",
                    headers={
                        "apikey": self.supabase_key,
                        "Authorization": f"Bearer {self.supabase_key}"
                    }
                )
                response.raise_for_status()
                data = response.json()
                return data[0] if len(data) > 0 else None
            except Exception as e:
                print(f"Auth check failed: {e}")
                return None

    async def log_request(self, api_key_id: int, model: str, provider: str, prompt_tokens: int, completion_tokens: int, cost: float):
        """Saves the log PERMANENTLY via direct REST API using required schema columns"""
        log_entry = {
            "api_key_id": api_key_id,  # Mandatory relational foreign key
            "model_used": model,
            # Note: 'provider' is intentionally omitted here to match your Supabase schema
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_cost": cost          # Matches your database column name exactly
        }
        
        self.current_spend += cost

        if self.supabase_url and self.supabase_key:
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        f"{self.supabase_url}/rest/v1/{self.table_name}",
                        headers={
                            "apikey": self.supabase_key,
                            "Authorization": f"Bearer {self.supabase_key}",
                            "Content-Type": "application/json",
                            "Prefer": "return=minimal"
                        },
                        json=log_entry
                    )
                    response.raise_for_status()
                except Exception as e:
                    print(f"Supabase Cloud Sync Error: {e}")

    async def fetch_logs(self):
        """Pulls the live ledger from Supabase via REST API"""
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
                    response.raise_for_status()
                    return response.json()
                except Exception as e:
                    print(f"Supabase Fetch Error: {e}")
                    return []
        return []

    def _determine_provider(self, model: str) -> str:
        if "llama" in model.lower() or "mixtral" in model.lower():
            return "groq"
        elif "deepseek" in model.lower():
            return "deepseek"
        elif "gemini" in model.lower():
            return "gemini"
        else:
            return "openrouter"

    async def route_request(self, api_key_id: int, user_id: str, prompt: str, requested_model: str = "llama-3.1-8b-instant"):
        if self.current_spend >= self.spend_caps.get(user_id, 10.00):
            return {"error": "Budget exceeded. Request blocked by ARKA Guardrail."}

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

        usage = ai_data.get("usage", {})
        p_tokens = usage.get("prompt_tokens", 0)
        c_tokens = usage.get("completion_tokens", 0)
        simulated_retail_cost = (p_tokens * 0.000001) + (c_tokens * 0.000002)

        # Send transaction to database linked with the originating token ID
        await self.log_request(api_key_id, requested_model, provider_name, p_tokens, c_tokens, simulated_retail_cost)
        
        return {
            "answer": ai_data["choices"][0]["message"]["content"],
            "model_used": requested_model,
            "provider": provider_name,
            "tokens": usage,
            "retail_value_saved": simulated_retail_cost
        }

arka_engine = ARKAOrchestrator()