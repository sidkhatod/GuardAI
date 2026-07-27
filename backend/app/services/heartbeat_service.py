import asyncio
import time
import hmac
import hashlib
import json
from uuid import UUID
from app.redis_client import get_redis
from app.db import get_pool
from app.services.ledger_service import LedgerService

class HeartbeatService:
    # Class-level dictionary to track background tasks in memory for this node
    _tasks = {}
    
    # Secret key for HMAC signing (in a real system, this would be an env var)
    HMAC_SECRET = b"super-secret-governance-key"
    HEARTBEAT_INTERVAL = 1.0

    @classmethod
    def start_heartbeat(cls, agent_id: UUID):
        # Cancel existing if restarting
        if agent_id in cls._tasks:
            cls._tasks[agent_id].cancel()
            
        task = asyncio.create_task(cls._heartbeat_loop(agent_id))
        cls._tasks[agent_id] = task

    @classmethod
    async def _heartbeat_loop(cls, agent_id: UUID):
        r = get_redis()
        try:
            while True:
                now = time.time()
                message = f"{agent_id}:{now}"
                signature = hmac.new(cls.HMAC_SECRET, message.encode(), hashlib.sha256).hexdigest()
                payload = json.dumps({"timestamp": now, "signature": signature})
                
                key = f"heartbeat:{agent_id}"
                # TTL is 2 * interval
                await r.set(key, payload, ex=int(cls.HEARTBEAT_INTERVAL * 2))
                
                # Publish tick to pub/sub
                await r.publish("heartbeat_broadcast", json.dumps({"agent_id": str(agent_id), "timestamp": now}))
                
                await asyncio.sleep(cls.HEARTBEAT_INTERVAL)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Heartbeat loop for {agent_id} crashed: {e}")

    @classmethod
    async def revoke_agent(cls, agent_id: UUID):
        # 1. Stop background loop if it exists locally
        if agent_id in cls._tasks:
            cls._tasks[agent_id].cancel()
            del cls._tasks[agent_id]
            
        # 2. Immediately delete the heartbeat key
        r = get_redis()
        await r.delete(f"heartbeat:{agent_id}")
        
        # 3. Update Postgres status
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE agents SET status = 'revoked' WHERE agent_id = $1", agent_id)
            
            # 4. Write to ledger
            ls = LedgerService()
            await ls.write(
                agent_id=agent_id,
                event_type="agent_revoked",
                payload={"reason": "Manual operator revocation"},
                policy_version="1.0.0"
            )
            
        await r.publish("agent_status_broadcast", json.dumps({"agent_id": str(agent_id), "status": "revoked"}))
            
        # 5. Trigger cascade quarantine
        await cls.cascade_quarantine(agent_id)

    @classmethod
    async def fleet_emergency_stop(cls):
        r = get_redis()
        # Increment epoch:global
        new_epoch = await r.incr("epoch:global")
        
        # Publish broadcast
        await r.publish("revoke_broadcast", json.dumps({"event": "fleet_emergency_stop", "new_epoch": new_epoch}))
        
        # Log to ledger
        ls = LedgerService()
        await ls.write(
            agent_id=None,
            event_type="fleet_emergency_stop",
            payload={"reason": "Manual operator fleet stop", "new_epoch": new_epoch},
            policy_version="1.0.0"
        )

    @classmethod
    async def cascade_quarantine(cls, producer_id: UUID):
        # Fetch consumers from Postgres
        pool = await get_pool()
        async with pool.acquire() as conn:
            consumers = await conn.fetch(
                "SELECT consumer_agent_id FROM agent_dependencies WHERE producer_agent_id = $1",
                producer_id
            )
            
            ls = LedgerService()
            r = get_redis()
            
            for row in consumers:
                consumer_id = row['consumer_agent_id']
                
                # 1. Stop local heartbeat if running
                if consumer_id in cls._tasks:
                    cls._tasks[consumer_id].cancel()
                    del cls._tasks[consumer_id]
                
                # 2. Delete heartbeat key from Redis
                await r.delete(f"heartbeat:{consumer_id}")
                
                # 3. Update status to 'quarantined'
                await conn.execute("UPDATE agents SET status = 'quarantined' WHERE agent_id = $1", consumer_id)
                
                # 4. Log to ledger
                await ls.write(
                    agent_id=consumer_id,
                    event_type="agent_quarantined",
                    payload={"reason": "Cascade revocation", "producer_id": str(producer_id)},
                    policy_version="1.0.0"
                )
                
                await r.publish("agent_status_broadcast", json.dumps({"agent_id": str(consumer_id), "status": "quarantined"}))
                
                # TODO: Recursive cascade (Stretch goal: call cascade_quarantine(consumer_id) here if depth > 1)
