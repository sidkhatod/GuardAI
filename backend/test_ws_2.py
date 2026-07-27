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
        
        # Start listening in background
        listen_task = asyncio.create_task(listen(ws))
        
        async with httpx.AsyncClient() as client:
            reg_resp = await client.post("http://localhost:8000/agents", json={
                "name": "WS Test Agent",
                "declared_task": "A test task",
                "base_spend_cap": 100.0,
                "merchant_category_scope": ["test"]
            })
            agent_id = reg_resp.json()["agent_id"]
            print(f"Registered agent: {agent_id}")
            
            # small delay to ensure agent is registered and broadcasted
            await asyncio.sleep(1)
            
            # Trigger high risk action (amount > 20)
            action_resp = await client.post(f"http://localhost:8000/agents/{agent_id}/action", json={
                "amount": 50.0,
                "merchant_category": "test",
                "action_type": "high_risk_test",
                "action_description": "High risk test"
            })
            print("Action Response:", action_resp.json())
            
        try:
            await asyncio.wait_for(listen_task, timeout=5.0)
        except asyncio.TimeoutError:
            print("TIMEOUT waiting for pending_approvals")

if __name__ == "__main__":
    asyncio.run(test_ws())
