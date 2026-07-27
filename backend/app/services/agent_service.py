import logging
from uuid import UUID, uuid4
from typing import List, Optional, Any
from pydantic import BaseModel
from fastapi import Request

from app.db import get_pool
from app.services.ledger_service import LedgerService

class AgentRegistrationRequest(BaseModel):
    name: str
    declared_task: str
    base_spend_cap: float
    merchant_category_scope: List[str]

class PolicyUpdateRequest(BaseModel):
    base_spend_cap: Optional[float] = None
    merchant_category_scope: Optional[List[str]] = None
    k1: Optional[float] = None
    k2: Optional[float] = None

class AgentService:
    async def register_agent(self, request: Request, data: AgentRegistrationRequest) -> dict:
        from app.redis_client import get_redis
        model = request.app.state.model
        agent_id = uuid4()
        
        # Get global epoch
        r = get_redis()
        global_epoch_raw = await r.get("epoch:global")
        global_epoch = int(global_epoch_raw) if global_epoch_raw else 1
        
        # Compute embedding
        import asyncio
        from app.main import cached_encode
        vector_array = await asyncio.to_thread(cached_encode, model, data.declared_task)
        vector = vector_array.tolist()
        
        pool = await get_pool()
        # Insert into agents table
        insert_query = """
            INSERT INTO agents (agent_id, name, declared_task, declared_intent_vector, base_spend_cap, merchant_category_scope, status, current_epoch)
            VALUES ($1, $2, $3, $4, $5, $6, 'active', $7)
            RETURNING *
        """
        
        inserted_row = await pool.fetchrow(
            insert_query,
            agent_id,
            data.name,
            data.declared_task,
            vector,
            data.base_spend_cap,
            data.merchant_category_scope,
            global_epoch
        )
        
        agent_record = dict(inserted_row)
        
        # Write to ledger
        ledger = LedgerService()
        ledger_payload = {
        "name": data.name,
        "declared_task": data.declared_task,
        "base_spend_cap": data.base_spend_cap,
        "merchant_category_scope": data.merchant_category_scope,
        "intent_vector_computed": True,
        "initial_epoch": global_epoch
        }
        await ledger.write(agent_id, "agent_registered", ledger_payload, "v1.0")
        
        import json
        await r.publish("agent_status_broadcast", json.dumps({"agent_id": str(agent_id), "status": "active"}))
        
        return agent_record

    async def get_agents(self) -> List[dict]:
        pool = await get_pool()
        rows = await pool.fetch("SELECT agent_id, name, declared_task, base_spend_cap, merchant_category_scope, status, current_epoch, k1, k2, created_at FROM agents ORDER BY created_at DESC")
        return [dict(r) for r in rows]

    async def update_policy(self, agent_id: UUID, req: PolicyUpdateRequest) -> dict:
        pool = await get_pool()
        # Fetch current values for diff
        old = await pool.fetchrow(
            "SELECT base_spend_cap, merchant_category_scope, k1, k2 FROM agents WHERE agent_id = $1", agent_id
        )
        if not old:
            return {"status": "error", "message": "Agent not found"}

        # Build update
        updates = {}
        if req.base_spend_cap is not None:
            updates["base_spend_cap"] = req.base_spend_cap
        if req.merchant_category_scope is not None:
            updates["merchant_category_scope"] = req.merchant_category_scope
        if req.k1 is not None:
            updates["k1"] = req.k1
        if req.k2 is not None:
            updates["k2"] = req.k2

        if not updates:
            return {"status": "no_changes"}

        set_clause = ", ".join(f"{col} = ${i+2}" for i, col in enumerate(updates.keys()))
        values = list(updates.values())
        await pool.execute(
            f"UPDATE agents SET {set_clause} WHERE agent_id = $1",
            agent_id, *values
        )

        # Build diff for ledger
        before = {k: (float(old[k]) if k in ('base_spend_cap', 'k1', 'k2') else list(old[k])) for k in updates}
        after = {k: (float(v) if k in ('base_spend_cap', 'k1', 'k2') else v) for k, v in updates.items()}

        ledger = LedgerService()
        await ledger.write(agent_id, "policy_updated", {"before": before, "after": after}, "v1.0")

        return {"status": "updated", "agent_id": str(agent_id), "changes": after}

    async def get_agent(self, agent_id: UUID) -> Optional[dict]:
        pool = await get_pool()
        row = await pool.fetchrow("SELECT * FROM agents WHERE agent_id = $1", agent_id)
        if row:
            return dict(row)
        return None

    async def rearm_agent(self, agent_id: UUID) -> dict:
        from app.redis_client import get_redis
        r = get_redis()
        global_epoch_raw = await r.get("epoch:global")
        global_epoch = int(global_epoch_raw) if global_epoch_raw else 1
        
        pool = await get_pool()
        await pool.execute("UPDATE agents SET current_epoch = $1 WHERE agent_id = $2", global_epoch, agent_id)
        
        # Write to ledger
        ledger = LedgerService()
        ledger_payload = {
        "reason": "Operator re-armed agent after fleet stop",
        "new_epoch": global_epoch
        }
        await ledger.write(agent_id, "agent_epoch_resynced", ledger_payload, "v1.0")
        
        import json
        await r.publish("agent_status_broadcast", json.dumps({"agent_id": str(agent_id), "status": "active"}))
        
        return {"status": "rearmed", "agent_id": str(agent_id), "current_epoch": global_epoch}
