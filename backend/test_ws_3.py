import asyncio
import websockets
import json
import httpx

async def listen(ws):
    while True:
        msg = await ws.recv()
        print("WS Received:", msg)
        data = json.loads(msg)
        if data.get("channel") == "pending_approvals":
            print("SUCCESS: pending_approvals received!")
            return True

async def test_ws():
    async with websockets.connect("ws://localhost:8000/ws/fleet") as ws:
        print("Connected to WS.")
        
        listen_task = asyncio.create_task(listen(ws))
        
        async with httpx.AsyncClient() as client:
            reg_resp = await client.post("http://localhost:8000/agents", json={
                "name": "WS Test Agent 3",
                "declared_task": "A test task",
                "base_spend_cap": 100.0,
                "merchant_category_scope": ["test"]
            })
            agent_id = reg_resp.json()["agent_id"]
            print(f"Registered agent: {agent_id}")
            
            # Pulse heartbeat
            hb_resp = await client.post(f"http://localhost:8000/agents/{agent_id}/heartbeat")
            print("Heartbeat:", hb_resp.json())
            
            await asyncio.sleep(0.5)
            
            # Trigger high risk action (amount > 20)
            # Run action asynchronously so we don't block
            action_task = asyncio.create_task(client.post(
                f"http://localhost:8000/agents/{agent_id}/action", 
                json={
                    "amount": 50.0,
                    "merchant_category": "test",
                    "action_type": "high_risk_test",
                    "action_description": "High risk test"
                }
            ))
            
        try:
            await asyncio.wait_for(listen_task, timeout=5.0)
        except asyncio.TimeoutError:
            print("TIMEOUT waiting for pending_approvals")

if __name__ == "__main__":
    asyncio.run(test_ws())
