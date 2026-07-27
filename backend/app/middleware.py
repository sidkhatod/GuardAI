import json
import re
from uuid import UUID
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.redis_client import get_redis
from app.db import get_pool
from app.services.ledger_service import LedgerService

class HeartbeatMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # We only check heartbeat on the action endpoint
        # Expected path: /agents/{agent_id}/action
        match = re.match(r"^/agents/([^/]+)/action$", request.url.path)
        
        if match and request.method == "POST":
            agent_id_str = match.group(1)
            try:
                agent_id = UUID(agent_id_str)
                r = get_redis()
                exists = await r.exists(f"heartbeat:{agent_id}")
                if not exists:
                    # Missing heartbeat: Fail fast and log to ledger
                    ls = LedgerService()
                    await ls.write(
                        agent_id=agent_id,
                        event_type="heartbeat_missed",
                        payload={"reason": "agent presumed dead, no heartbeat"},
                        policy_version="1.0.0"
                    )
                    
                    return Response(
                        content=json.dumps({"status": "deny", "reason": "heartbeat_missed"}),
                        status_code=403,
                        media_type="application/json"
                    )
                    
                # Epoch Check
                global_epoch_raw = await r.get("epoch:global")
                global_epoch = int(global_epoch_raw) if global_epoch_raw else 1
                
                pool = await get_pool()
                async with pool.acquire() as conn:
                    agent = await conn.fetchrow("SELECT current_epoch FROM agents WHERE agent_id = $1", agent_id)
                    if agent and agent["current_epoch"] != global_epoch:
                        ls = LedgerService()
                        await ls.write(
                            agent_id=agent_id,
                            event_type="action_denied",
                            payload={"reason": "epoch_mismatch", "expected": global_epoch, "actual": agent["current_epoch"]},
                            policy_version="1.0.0"
                        )
                        
                        return Response(
                            content=json.dumps({"status": "deny", "reason": "epoch_mismatch"}),
                            status_code=403,
                            media_type="application/json"
                        )
                        
            except ValueError:
                pass # Invalid UUID, let downstream handle validation

        return await call_next(request)
