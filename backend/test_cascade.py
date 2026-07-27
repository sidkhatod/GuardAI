import asyncio
import httpx
from uuid import uuid4
from app.main import app
from app.db import get_pool
from sentence_transformers import SentenceTransformer
from app.redis_client import get_redis

async def main():
    print("Loading model for test...")
    app.state.model = SentenceTransformer("all-MiniLM-L6-v2")
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 1 & 2: Setup Producer and Consumer
        print("\n1. Setup Producer and Consumer")
        producer_req = await client.post("/agents", json={
            "name": "producer",
            "declared_task": "produce data",
            "base_spend_cap": 1000.0,
            "merchant_category_scope": ["test"]
        })
        producer_id = producer_req.json()["agent_id"]
        
        consumer_req = await client.post("/agents", json={
            "name": "consumer",
            "declared_task": "consume data",
            "base_spend_cap": 500.0,
            "merchant_category_scope": ["test"]
        })
        consumer_id = consumer_req.json()["agent_id"]
        
        # Link them
        await client.post(f"/agents/{consumer_id}/depends-on/{producer_id}")
        
        # Start heartbeats
        await client.post(f"/agents/{producer_id}/heartbeat/start")
        await client.post(f"/agents/{consumer_id}/heartbeat/start")
        print(f"Producer ({producer_id}) and Consumer ({consumer_id}) started.")
        
        # Give heartbeats a moment to write to redis
        await asyncio.sleep(0.5)
        
        # Step 3: Revoke Producer
        print("\n2. Revoking Producer to trigger cascade")
        await client.post(f"/agents/{producer_id}/revoke")
        
        # Wait a moment for async cascade logic
        await asyncio.sleep(0.5)
        
        # Step 4: Confirm Consumer quarantined
        print("\n3. Verifying Consumer Quarantine")
        action_payload = {
            "amount": 10.0,
            "merchant_category": "test",
            "description": "test action"
        }
        resp = await client.post(f"/agents/{consumer_id}/action", json=action_payload)
        print(f"Consumer action response: HTTP {resp.status_code} - {resp.json()}")
        assert resp.status_code == 403
        assert resp.json()["reason"] == "heartbeat_missed"
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            consumer_row = await conn.fetchrow("SELECT status FROM agents WHERE agent_id = $1", consumer_id)
            assert consumer_row["status"] == "quarantined"
            
            ledger_row = await conn.fetchrow("SELECT event_type FROM ledger_entries WHERE agent_id = $1 AND event_type = 'agent_quarantined' ORDER BY entry_id DESC LIMIT 1", consumer_id)
            assert ledger_row is not None and ledger_row["event_type"] == "agent_quarantined"
        print("Consumer was correctly quarantined!")

        # Setup an independent agent for epoch testing
        indep_req = await client.post("/agents", json={
            "name": "independent",
            "declared_task": "independent task",
            "base_spend_cap": 1000.0,
            "merchant_category_scope": ["test"]
        })
        indep_id = indep_req.json()["agent_id"]
        await client.post(f"/agents/{indep_id}/heartbeat/start")
        await asyncio.sleep(0.5)
        
        # Step 5: Fire Fleet-Wide Stop
        print("\n4. Firing Fleet-Wide Stop")
        await client.post("/fleet/emergency-stop")
        
        # Step 6: Confirm Independent Agent denied via epoch_mismatch
        print("\n5. Verifying Epoch Mismatch on existing agent")
        resp = await client.post(f"/agents/{indep_id}/action", json=action_payload)
        print(f"Independent agent action response: HTTP {resp.status_code} - {resp.json()}")
        assert resp.status_code == 403
        assert resp.json()["reason"] == "epoch_mismatch"
        print("Independent agent correctly fenced via epoch!")

        # Step 7: Register brand new agent
        print("\n6. Testing new agent sync")
        new_req = await client.post("/agents", json={
            "name": "newcomer",
            "declared_task": "newcomer task",
            "base_spend_cap": 1000.0,
            "merchant_category_scope": ["test"]
        })
        new_id = new_req.json()["agent_id"]
        await client.post(f"/agents/{new_id}/heartbeat/start")
        await asyncio.sleep(0.5)
        
        resp = await client.post(f"/agents/{new_id}/action", json=action_payload)
        print(f"New agent action response: HTTP {resp.status_code} - {resp.json()}")
        assert resp.status_code == 200, "Should bypass epoch block and reach policy logic"
        print("New agent correctly synced with global epoch!")

        # Step 8: Re-arm Independent Agent
        print("\n7. Testing Re-arm of fenced agent")
        await client.post(f"/agents/{indep_id}/re-arm")
        resp = await client.post(f"/agents/{indep_id}/action", json=action_payload)
        print(f"Re-armed agent action response: HTTP {resp.status_code} - {resp.json()}")
        assert resp.status_code == 200
        print("Independent agent successfully re-armed!")

        print("\nAll Cascade and Epoch tests passed!")

if __name__ == "__main__":
    asyncio.run(main())
