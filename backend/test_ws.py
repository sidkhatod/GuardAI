import asyncio
import websockets
import json
import httpx

async def test_ws():
    async with websockets.connect("ws://localhost:8000/ws/fleet") as ws:
        print("Connected to WS.")
        
        # 1. Create an agent
        async with httpx.AsyncClient() as client:
            reg_resp = await client.post("http://localhost:8000/agents", json={
                "name": "Test Agent for WS",
                "declared_task": "A test task",
                "base_spend_cap": 1000.0,
                "merchant_category_scope": ["test"]
            })
            agent_id = reg_resp.json()["agent_id"]
            print(f"Registered agent: {agent_id}")
            
            # Wait for agent_status_broadcast (active)
            msg1 = await ws.recv()
            print("WS Received:", msg1)
            
            # 2. Trigger high risk action (amount > 200)
            action_resp = await client.post(f"http://localhost:8000/agents/{agent_id}/action", json={
                "amount": 500.0,
                "merchant_category": "test",
                "action_type": "high_risk_test",
                "action_description": "High risk test"
            })
            print("Action Response:", action_resp.json())
            
        # 3. Read incoming WS messages until pending_approval is found or timeout
        try:
            for _ in range(5): # Check next 5 messages max
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                print("WS Received:", msg)
                data = json.loads(msg)
                if data.get("channel") == "pending_approvals":
                    print("SUCCESS: pending_approvals received!")
                    return
        except asyncio.TimeoutError:
            print("TIMEOUT waiting for pending_approvals")
            
        print("FAILED to receive pending_approvals")

if __name__ == "__main__":
    asyncio.run(test_ws())
