from fastapi import HTTPException, Security, Request
from fastapi.security import APIKeyHeader
from app.services.orchestrator import arka_engine

api_key_header = APIKeyHeader(name="X-ARKA-Key", auto_error=True)

async def verify_agent_credit(request: Request, api_key: str = Security(api_key_header)):
    """
    Production Guard: Intercepts machine requests, maps identities,
    evaluates financial ledgers, and applies token rate-limiting.
    """
    agent_id = await arka_engine.redis.hget(f"api_key:{api_key}", "agent_id")
    if not agent_id:
        raise HTTPException(status_code=401, detail="Unauthorized API Key.")

    key_status = await arka_engine.redis.hget(f"api_key:{api_key}", "status")
    if key_status == "suspended":
        raise HTTPException(status_code=403, detail="API key suspended.")

    current_balance = await arka_engine.redis.hget(f"wallet:{agent_id}", "balance")
    if current_balance is None or float(current_balance) <= 0.0: 
        raise HTTPException(status_code=402, detail="Payment Required. Wallet empty.")

    rate_limit_key = f"rate_limit:{agent_id}"
    requests_last_minute = await arka_engine.redis.incr(rate_limit_key)
    
    if requests_last_minute == 1:
        await arka_engine.redis.expire(rate_limit_key, 60)
        
    if requests_last_minute > 100: 
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")
        
    request.state.agent_id = agent_id
    return agent_id