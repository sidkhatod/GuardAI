import time
import requests
import sys

BASE_URL = "http://127.0.0.1:8000"

def run_tests():
    print("Testing POST /agents...")
    payload = {
        "name": "fx-agent-1",
        "declared_task": "fx_hedge_execution",
        "base_spend_cap": 5000,
        "merchant_category_scope": ["fx"]
    }
    resp = requests.post(f"{BASE_URL}/agents", json=payload)
    if resp.status_code != 200:
        print(f"POST /agents failed: {resp.text}")
        sys.exit(1)
    
    agent_data = resp.json()
    agent_id = agent_data.get("agent_id")
    print(f"Got valid agent_id: {agent_id}")
    
    print("\nTesting GET /ledger...")
    ledger_resp = requests.get(f"{BASE_URL}/ledger")
    ledger_entries = ledger_resp.json()
    agent_registered_entry = next((e for e in ledger_entries if e["event_type"] == "agent_registered" and "fx-agent-1" in e["payload"]), None)
    if agent_registered_entry:
        print("Found agent_registered entry in ledger!")
    else:
        print("Failed to find agent_registered entry in ledger")
        sys.exit(1)
        
    print("\nTesting POST /ledger/verify...")
    verify_resp = requests.post(f"{BASE_URL}/ledger/verify")
    print(f"Verify response: {verify_resp.json()}")
    if not verify_resp.json().get("valid"):
        print("Ledger verification failed!")
        sys.exit(1)

    print("\nTesting GET /agents...")
    agents_resp = requests.get(f"{BASE_URL}/agents")
    agents = agents_resp.json()
    if any(a.get("name") == "fx-agent-1" for a in agents):
        print("Found agent in GET /agents list!")
    else:
        print("Agent not found in list")
        sys.exit(1)

    print(f"\nTesting GET /agents/{{agent_id}}...")
    agent_resp = requests.get(f"{BASE_URL}/agents/{agent_id}")
    if agent_resp.status_code == 200 and agent_resp.json().get("name") == "fx-agent-1":
        print("GET /agents/{agent_id} works!")
    else:
        print("GET /agents/{agent_id} failed!")
        sys.exit(1)

    print("\nTesting GET /agents/{random_uuid} (404 check)...")
    import uuid
    random_id = str(uuid.uuid4())
    random_resp = requests.get(f"{BASE_URL}/agents/{random_id}")
    if random_resp.status_code == 404:
        print("Got 404 for random UUID successfully!")
    else:
        print(f"Expected 404, got {random_resp.status_code}")
        sys.exit(1)
        
    print("\nAll tests passed!")

if __name__ == "__main__":
    run_tests()
