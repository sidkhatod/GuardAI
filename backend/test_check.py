import asyncio
import httpx
from uuid import uuid4
from app.main import app
from app.db import get_pool
from sentence_transformers import SentenceTransformer

async def main():
    print("Loading model for test...")
    app.state.model = SentenceTransformer("all-MiniLM-L6-v2")
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        action_payload = {
            "amount": 10.0,
            "merchant_category": "test",
            "description": "test action"
        }
        
        print("\n--- SCENARIO 1: CASCADE REVOCATION ---")
        # Start two agents A and B
        req_a = await client.post("/agents", json={"name": "A", "declared_task": "task A", "base_spend_cap": 1000.0, "merchant_category_scope": ["test"]})
        agent_a_id = req_a.json()["agent_id"]
        
        req_b = await client.post("/agents", json={"name": "B", "declared_task": "task B", "base_spend_cap": 1000.0, "merchant_category_scope": ["test"]})
        agent_b_id = req_b.json()["agent_id"]
        
        # B depends on A
        await client.post(f"/agents/{agent_b_id}/depends-on/{agent_a_id}")
        
        # Start heartbeats
        await client.post(f"/agents/{agent_a_id}/heartbeat/start")
        await client.post(f"/agents/{agent_b_id}/heartbeat/start")
        await asyncio.sleep(0.5)
        
        # Confirm both pass normal actions
        resp_a = await client.post(f"/agents/{agent_a_id}/action", json=action_payload)
        resp_b = await client.post(f"/agents/{agent_b_id}/action", json=action_payload)
        assert resp_a.status_code == 200, f"A failed: {resp_a.json()}"
        assert resp_b.status_code == 200, f"B failed: {resp_b.json()}"
        print("A and B passed normal action requests.")
        
        # Revoke A
        await client.post(f"/agents/{agent_a_id}/revoke")
        await asyncio.sleep(0.5)
        
        # Confirm A is fenced (heartbeat missed)
        resp_a2 = await client.post(f"/agents/{agent_a_id}/action", json=action_payload)
        assert resp_a2.status_code == 403
        assert resp_a2.json()["reason"] == "heartbeat_missed"
        print("A is immediately fenced after revocation.")
        
        # Confirm B is quarantined in PG and heartbeat stopped
        pool = await get_pool()
        async with pool.acquire() as conn:
            status_b = await conn.fetchval("SELECT status FROM agents WHERE agent_id = $1", agent_b_id)
            assert status_b == "quarantined"
            print("B's status flipped to 'quarantined' in Postgres.")
            
        resp_b2 = await client.post(f"/agents/{agent_b_id}/action", json=action_payload)
        assert resp_b2.status_code == 403
        assert resp_b2.json()["reason"] == "heartbeat_missed"
        print("B's action request is denied because heartbeat was stopped via cascade.")
        
        print("\n--- SCENARIO 2: FLEET-WIDE STOP ---")
        # Reset, start fresh A2 and B2
        req_a2 = await client.post("/agents", json={"name": "A2", "declared_task": "task A2", "base_spend_cap": 1000.0, "merchant_category_scope": ["test"]})
        agent_a2_id = req_a2.json()["agent_id"]
        
        req_b2 = await client.post("/agents", json={"name": "B2", "declared_task": "task B2", "base_spend_cap": 1000.0, "merchant_category_scope": ["test"]})
        agent_b2_id = req_b2.json()["agent_id"]
        
        await client.post(f"/agents/{agent_b2_id}/depends-on/{agent_a2_id}")
        await client.post(f"/agents/{agent_a2_id}/heartbeat/start")
        await client.post(f"/agents/{agent_b2_id}/heartbeat/start")
        await asyncio.sleep(0.5)
        
        # Fleet stop
        await client.post("/fleet/emergency-stop")
        await asyncio.sleep(0.1) # just to be safe
        
        # Confirm both are denied via epoch_mismatch
        resp_a3 = await client.post(f"/agents/{agent_a2_id}/action", json=action_payload)
        assert resp_a3.status_code == 403
        assert resp_a3.json()["reason"] == "epoch_mismatch"
        
        resp_b3 = await client.post(f"/agents/{agent_b2_id}/action", json=action_payload)
        assert resp_b3.status_code == 403
        assert resp_b3.json()["reason"] == "epoch_mismatch"
        print("BOTH A2 and B2 are immediately denied via epoch_mismatch, even with fresh heartbeats!")
        
        # Ledger check for cascade
        print("\n--- VERIFYING LEDGER ---")
        async with pool.acquire() as conn:
            # Check cascade entry for B
            ledger_row_b = await conn.fetchrow("SELECT payload, event_type FROM ledger_entries WHERE agent_id = $1 AND event_type = 'agent_quarantined' ORDER BY entry_id DESC LIMIT 1", agent_b_id)
            assert ledger_row_b is not None
            import json
            payload = json.loads(ledger_row_b["payload"]) if isinstance(ledger_row_b["payload"], str) else ledger_row_b["payload"]
            assert payload["producer_id"] == str(agent_a_id)
            print("Ledger correctly shows quarantine event referencing the producer that triggered it.")
            
            # Check epoch mismatch events for A2 and B2
            ledger_row_a2 = await conn.fetchrow("SELECT event_type FROM ledger_entries WHERE agent_id = $1 AND event_type = 'action_denied' ORDER BY entry_id DESC LIMIT 1", agent_a2_id)
            assert ledger_row_a2["event_type"] == "action_denied"
            
            ledger_row_b2 = await conn.fetchrow("SELECT event_type FROM ledger_entries WHERE agent_id = $1 AND event_type = 'action_denied' ORDER BY entry_id DESC LIMIT 1", agent_b2_id)
            assert ledger_row_b2["event_type"] == "action_denied"
            print("Ledger recorded epoch_mismatch action_denied events.")
            
        # Verify chain
        verify_resp = await client.post("/ledger/verify")
        assert verify_resp.status_code == 200
        assert verify_resp.json()["valid"] == True
        print("Ledger chain successfully verified!")

if __name__ == "__main__":
    asyncio.run(main())
