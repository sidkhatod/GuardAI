from uuid import UUID, uuid4
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
from typing import Optional
import json

from app.db import get_pool
from app.services.ledger_service import LedgerService
from app.services.fallback_evaluator import JSONRuleEvaluator, DEFAULT_POLICY_JSON

class TokenRequest(BaseModel):
    amount: float
    merchant_category: str
    action_type: str = "initiate_transfer"
    action_description: str = ""

class ApproveSplitAuthRequest(BaseModel):
    approval_id: str
    decision: str
    operator_session_id: str

class TokenService:
    def __init__(self, model=None):
        self.evaluator = JSONRuleEvaluator(DEFAULT_POLICY_JSON)
        self.ledger = LedgerService()
        from app.services.envelope_service import EnvelopeService
        self.envelope_service = EnvelopeService()
        self.model = model

    async def request_token(self, agent_id: UUID, req: TokenRequest) -> dict:
        pool = await get_pool()
        # 1. Get agent
        agent = await pool.fetchrow("SELECT * FROM agents WHERE agent_id = $1", agent_id)
        if not agent:
            reason = f"Agent not found: {agent_id}"
            await self.ledger.write(agent_id, "action_denied", {"reason": reason, "request": json.loads(req.json())}, "v1.0")
            return {"status": "deny", "reason": reason}
        
        if agent["status"] != "active":
            reason = f"Agent is not active: {agent_id}"
            await self.ledger.write(agent_id, "action_denied", {"reason": reason, "request": json.loads(req.json())}, "v1.0")
            return {"status": "deny", "reason": reason}

        # Prepare context for policy evaluation
        principal_id = f'Agent::"{agent["name"]}"'
        action_id = f'PaymentAction::"{req.action_type}"'
        resource_id = f'MerchantCategory::"{req.merchant_category}"'
        
        context = {
            "amount": req.amount,
            "epoch": agent["current_epoch"],
            "dual_control_approved": True  # Assume true for evaluation; we enforce it via the high-risk path
        }
        
        principal_attrs = {
            "effective_cap": float(agent["base_spend_cap"]), # Dynamic effective_cap is now applied via EnvelopeService
            "base_cap": float(agent["base_spend_cap"]),
            "current_epoch": agent["current_epoch"]
        }
        
        # 1. Envelope Service Dynamic Check
        if self.model:
            import asyncio
            from app.main import cached_encode
            current_action_embedding_array = await asyncio.to_thread(cached_encode, self.model, req.action_description)
            current_action_embedding = current_action_embedding_array.tolist()
        else:
            # Fallback for tests if no model provided
            current_action_embedding = [0.0] * 384
            
        declared_intent_vector = json.loads(agent["declared_intent_vector"]) if isinstance(agent["declared_intent_vector"], str) else agent["declared_intent_vector"]
        
        env_res = await self.envelope_service.check_envelope(
            agent_id=agent_id,
            base_cap=float(agent["base_spend_cap"]),
            declared_intent_vector=declared_intent_vector,
            current_action_embedding=current_action_embedding,
            amount=req.amount,
            k1=float(agent["k1"]) if agent["k1"] is not None else None,
            k2=float(agent["k2"]) if agent["k2"] is not None else None,
        )
        
        env_stats = {
            "effective_cap": env_res["effective_cap"],
            "intent_multiplier": env_res["intent_multiplier"],
            "loss_ratio_multiplier": env_res["loss_ratio_multiplier"],
            "divergence_score": env_res["divergence_score"],
            "loss_ratio": env_res["loss_ratio"],
            "current_window_sum": env_res["current_window_sum"]
        }
        
        if not env_res["allowed"]:
            reason = "envelope_exceeded"
            await self.ledger.write(agent_id, "action_denied", {"reason": reason, "request": json.loads(req.json()), "envelope_stats": env_stats}, "v1.0")
            return {"status": "deny", "reason": reason}
        
        # Evaluate policy
        is_authorized = self.evaluator.is_authorized(
            principal_id=principal_id,
            action_id=action_id,
            resource_id=resource_id,
            context=context,
            principal_attrs=principal_attrs
        )
        
        if not is_authorized:
            reason = "Policy denied request: Amount exceeds limits, epoch mismatch, or unauthorized action/resource."
            await self.ledger.write(agent_id, "action_denied", {"reason": reason, "request": json.loads(req.json())}, "v1.0")
            return {"status": "deny", "reason": reason}
            
        # Low-risk token issuance
        low_risk_threshold = float(agent["base_spend_cap"]) * 0.2
        if req.amount <= low_risk_threshold:
            token_id = uuid4()
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=60)
            scope = f"{req.action_type}:{req.merchant_category}:{req.amount}"
            
            insert_query = """
                INSERT INTO capability_tokens (
                    token_id, agent_id, scope, requires_dual_control, 
                    combined_and_valid, expires_at, epoch_at_issue
                )
                VALUES ($1, $2, $3, false, true, $4, $5)
                RETURNING *
            """
            
            row = await pool.fetchrow(
                insert_query,
                token_id,
                agent_id,
                scope,
                expires_at,
                agent["current_epoch"]
            )
            
            # Log issuance
            await self.ledger.write(
                agent_id, 
                "token_issued", 
                {"token_id": str(token_id), "scope": scope, "type": "low-risk", "envelope_stats": env_stats}, 
                "v1.0"
            )
            
            return {
                "status": "allow", 
                "token": dict(row)
            }
        else:
            # High-risk path
            approval_id = uuid4()
            payload = json.loads(req.json())
            
            # Create pending approval
            await pool.execute("""
                INSERT INTO pending_approvals (approval_id, agent_id, request_payload, status)
                VALUES ($1, $2, $3::jsonb, 'pending')
            """, approval_id, agent_id, json.dumps(payload))
            
            # Publish to Redis
            import json as json_mod
            from app.redis_client import get_redis
            import asyncio
            r = get_redis()
            pub_payload = {
                "approval_id": str(approval_id),
                "agent_id": str(agent_id),
                "amount": req.amount,
                "merchant_category": req.merchant_category,
                "action_type": req.action_type,
                "envelope_stats": env_stats
            }
            await r.publish("pending_approvals", json_mod.dumps(pub_payload))
            
            # Block/poll for resolution
            for _ in range(30):
                await asyncio.sleep(1)
                row = await pool.fetchrow("SELECT status, operator_session_id FROM pending_approvals WHERE approval_id = $1", approval_id)
                if row["status"] == "approved":
                    # Issue token
                    token_id = uuid4()
                    expires_at = datetime.now(timezone.utc) + timedelta(seconds=60)
                    scope = f"{req.action_type}:{req.merchant_category}:{req.amount}"
                    
                    insert_query = """
                        INSERT INTO capability_tokens (
                            token_id, agent_id, scope, requires_dual_control, 
                            dual_control_approved_by, combined_and_valid, expires_at, epoch_at_issue
                        )
                        VALUES ($1, $2, $3, true, $4, true, $5, $6)
                        RETURNING *
                    """
                    token_row = await pool.fetchrow(
                        insert_query, token_id, agent_id, scope, row["operator_session_id"], expires_at, agent["current_epoch"]
                    )
                    
                    await self.ledger.write(
                        agent_id, 
                        "token_issued", 
                        {"token_id": str(token_id), "scope": scope, "type": "high-risk", "dual_control_approved_by": row["operator_session_id"], "envelope_stats": env_stats}, 
                        "v1.0"
                    )
                    return {"status": "allow", "token": dict(token_row)}
                elif row["status"] == "denied":
                    reason = "dual_control_denied_by_operator"
                    await self.ledger.write(agent_id, "action_denied", {"reason": reason, "request": payload}, "v1.0")
                    return {"status": "deny", "reason": reason}
                    
            # Timeout
            await pool.execute("UPDATE pending_approvals SET status = 'timeout' WHERE approval_id = $1", approval_id)
            reason = "dual_control_timeout"
            await self.ledger.write(agent_id, "action_denied", {"reason": reason, "request": payload}, "v1.0")
            return {"status": "deny", "reason": reason}

    async def approve_split_auth(self, req: ApproveSplitAuthRequest) -> dict:
        pool = await get_pool()
        from uuid import UUID
        row = await pool.fetchrow("SELECT * FROM pending_approvals WHERE approval_id = $1", UUID(req.approval_id))
        if not row:
            return {"status": "error", "message": "Approval ID not found"}
        if row["status"] != "pending":
            return {"status": "error", "message": f"Approval already resolved: {row['status']}"}
        
        new_status = "approved" if req.decision == "approve" else "denied"
        await pool.execute("UPDATE pending_approvals SET status = $1, operator_session_id = $2 WHERE approval_id = $3", new_status, req.operator_session_id, UUID(req.approval_id))
        
        return {"status": "success", "decision": new_status}

    async def resolve_token(self, agent_id: UUID, token_id: UUID, success: bool) -> dict:
        pool = await get_pool()
        row = await pool.fetchrow("SELECT agent_id FROM capability_tokens WHERE token_id = $1", token_id)
        if not row:
            return {"status": "error", "message": "Token not found"}
            
        token_agent_id = row["agent_id"]
        if token_agent_id != agent_id:
            return {"status": "error", "message": "Agent ID mismatch"}
        
        # Increment Redis counter
        from app.redis_client import get_redis
        r = get_redis()
        
        if success:
            await r.incr(f"lossratio:{agent_id}:success")
        else:
            await r.incr(f"lossratio:{agent_id}:failure")
            
        # Log resolution
        await self.ledger.write(agent_id, "spend_recorded", {"token_id": str(token_id), "success": success}, "v1.0")
        
        return {"status": "success"}
