import asyncio
import httpx
import time

async def setup():
    async with httpx.AsyncClient() as client:
        # Create Agent 1 (Producer)
        resp1 = await client.post("http://localhost:8000/agents", json={
            "name": "Producer Agent A",
            "declared_task": "Generate data",
            "base_spend_cap": 500.0,
            "merchant_category_scope": ["data"]
        })
        agent_a = resp1.json()["agent_id"]
        
        # Create Agent 2 (Consumer)
        resp2 = await client.post("http://localhost:8000/agents", json={
            "name": "Consumer Agent B",
            "declared_task": "Consume data from A",
            "base_spend_cap": 250.0,
            "merchant_category_scope": ["processing"]
        })
        agent_b = resp2.json()["agent_id"]
        
        # Create Agent 3 (Independent)
        resp3 = await client.post("http://localhost:8000/agents", json={
            "name": "Independent Agent C",
            "declared_task": "Run solo",
            "base_spend_cap": 1000.0,
            "merchant_category_scope": ["misc"]
        })
        agent_c = resp3.json()["agent_id"]
        
        print(f"Created Agents:\nA: {agent_a}\nB: {agent_b}\nC: {agent_c}")
        
        # Set dependency: B depends on A
        dep_resp = await client.post(f"http://localhost:8000/agents/{agent_b}/depends-on/{agent_a}")
        print(f"Dependency set: B depends on A -> {dep_resp.status_code}")
        
        # Start heartbeats for all 3
        await client.post(f"http://localhost:8000/agents/{agent_a}/heartbeat/start")
        await client.post(f"http://localhost:8000/agents/{agent_b}/heartbeat/start")
        await client.post(f"http://localhost:8000/agents/{agent_c}/heartbeat/start")
        print("Heartbeats started for all 3 agents.")
        
        print("\nSetup complete. You can now verify the dashboard!")

if __name__ == "__main__":
    asyncio.run(setup())
