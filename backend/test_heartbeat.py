import asyncio
import httpx
import time

async def test_heartbeat():
    async with httpx.AsyncClient() as client:
        # 1. Register an agent
        print("Registering agent...")
        reg_resp = await client.post("http://localhost:8000/agents", json={
            "name": "Heartbeat Agent",
            "declared_task": "Stay alive",
            "base_spend_cap": 100.0,
            "merchant_category_scope": ["test"]
        })
        agent_id = reg_resp.json()["agent_id"]
        print(f"Agent registered: {agent_id}")
        
        # 2. Start heartbeat (this kicks off the background task in backend)
        print(f"Starting heartbeat for {agent_id}...")
        hb_resp = await client.post(f"http://localhost:8000/agents/{agent_id}/heartbeat/start")
        print("Heartbeat start response:", hb_resp.json())
        
        print("\nThe backend is now pulsing heartbeats.")
        print("Check your browser console to see the [Fleet WS] heartbeat_broadcast events.")
        
if __name__ == "__main__":
    asyncio.run(test_heartbeat())
