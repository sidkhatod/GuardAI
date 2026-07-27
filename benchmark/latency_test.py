import asyncio
import httpx
import json
import time
import argparse
import asyncpg
from typing import List, Dict, Any
from urllib.parse import urljoin

BASE_URL = "http://localhost:8000"
DB_DSN = "postgresql://governance:governance_dev@localhost:5432/governance"

# ── PART B: POLICY ACCURACY ──────────────────────────────────────────────────

async def run_accuracy_test(client: httpx.AsyncClient, fixture: Dict[str, Any]) -> bool:
    print(f"Running case: {fixture['id']}...")
    
    setup = fixture["agent_setup"]
    action = fixture["action"]
    expected = fixture["expected_outcome"]
    
    # 1. Register agent
    r = await client.post(f"{BASE_URL}/agents", json={
        "name": setup.get("name", "agent-alpha"), # agent-alpha by default to pass Cedar
        "declared_task": "test task",
        "base_spend_cap": float(setup["base_spend_cap"]),
        "merchant_category_scope": setup["merchant_category_scope"]
    })
    
    if r.status_code != 200:
        print(f"  [!] Failed to register agent: {r.text}")
        return False
        
    agent_id = r.json()["agent_id"]
    
    # 2. Setup agent state
    if not setup.get("stop_heartbeat"):
        await client.post(f"{BASE_URL}/agents/{agent_id}/heartbeat/start")
        
    if setup.get("bump_epoch"):
        # trigger emergency stop to bump epoch globally, making this agent's epoch stale
        await client.post(f"{BASE_URL}/fleet/emergency-stop")
        
    if "policy_override" in setup:
        await client.patch(f"{BASE_URL}/agents/{agent_id}/policy", json=setup["policy_override"])
        
    # Wait for state to settle
    await asyncio.sleep(0.5)
    
    # 3. Fire action request
    action_task = asyncio.create_task(
        client.post(f"{BASE_URL}/agents/{agent_id}/action", json=action)
    )
    
    # 4. Handle Dual Control if necessary
    if expected.startswith("dual_control"):
        # wait a moment for the pending approval to hit the DB
        await asyncio.sleep(1.0)
        conn = await asyncpg.connect(DB_DSN)
        row = await conn.fetchrow(
            "SELECT approval_id FROM pending_approvals WHERE agent_id = $1 AND status = 'pending' ORDER BY created_at DESC LIMIT 1", 
            agent_id
        )
        if not row:
            print(f"  [FAIL] Expected dual control, but no pending approval found in DB.")
            action_task.cancel()
            await conn.close()
            return False
            
        approval_id = str(row["approval_id"])
        
        if expected == "dual_control_approve":
            decision = "approve"
        elif expected == "dual_control_deny":
            decision = "deny"
        else:
            # Just 'dual_control' means we just wanted to see if it hit dual control
            decision = "deny"
            
        # Call the split auth endpoint
        await client.post(f"{BASE_URL}/agents/{agent_id}/approve-split-auth", json={
            "approval_id": approval_id,
            "decision": decision,
            "operator_session_id": "test-operator"
        })
        await conn.close()
        
    # 5. Await response
    try:
        resp = await action_task
        result = resp.json()
    except Exception as e:
        print(f"  [!] Request error: {e}")
        return False

    status = result.get("status")
    reason = result.get("reason", "")
    
    # 6. Evaluate outcome
    passed = False
    actual_outcome = f"{status}:{reason}"
    
    if expected == "allow" and status == "allow":
        passed = True
    elif expected == "deny" and status == "deny":
        passed = True
    elif expected == "deny_heartbeat" and status == "deny" and "heartbeat" in reason.lower():
        passed = True
    elif expected == "deny_epoch" and status == "deny" and "epoch" in reason.lower():
        passed = True
    elif expected == "deny_cedar" and status == "deny" and "policy denied" in reason.lower():
        passed = True
    elif expected == "deny_envelope" and status == "deny" and "envelope" in reason.lower():
        passed = True
    elif expected == "dual_control" and status == "deny" and "dual_control" in reason.lower():
        passed = True
    elif expected == "dual_control_approve" and status == "allow":
        passed = True
    elif expected == "dual_control_deny" and status == "deny" and "dual_control" in reason.lower():
        passed = True
        
    if passed:
        print(f"  [PASS] Expected: {expected}, Got: {actual_outcome}")
    else:
        print(f"  [FAIL] Expected: {expected}, Got: {actual_outcome}")
        
    return passed

async def run_all_accuracy_tests():
    print("\n" + "="*60)
    print("  PART B: POLICY ENFORCEMENT ACCURACY")
    print("="*60)
    
    with open("benchmark/accuracy_fixtures.json", "r") as f:
        fixtures = json.load(f)
        
    passed_count = 0
    total_count = len(fixtures)
    
    async with httpx.AsyncClient(timeout=120) as client:
        for fixture in fixtures:
            if await run_accuracy_test(client, fixture):
                passed_count += 1
            await asyncio.sleep(0.5) # breather between tests
            
    print("-" * 60)
    print(f"Accuracy Result: {passed_count}/{total_count} policy accuracy tests passed.")
    print("-" * 60 + "\n")
    return passed_count, total_count

# ── PART A: LATENCY ──────────────────────────────────────────────────────────

async def fire_request(client: httpx.AsyncClient, agent_id: str, payload: dict) -> float:
    start_time = time.perf_counter()
    try:
        r = await client.post(f"{BASE_URL}/agents/{agent_id}/action", json=payload)
        r.raise_for_status()
    except Exception as e:
        print(f"Request failed: {e}")
        return None
    end_time = time.perf_counter()
    return (end_time - start_time) * 1000  # ms

async def run_latency_test(concurrency: int):
    print("\n" + "="*60)
    print(f"  PART A: LATENCY IMPACT (N={concurrency} concurrent requests)")
    print("="*60)
    
    limits = httpx.Limits(max_connections=1000, max_keepalive_connections=100)
    async with httpx.AsyncClient(timeout=60, limits=limits) as client:
        # Register a warm agent
        r = await client.post(f"{BASE_URL}/agents", json={
            "name": "agent-alpha",
            "declared_task": "load testing",
            "base_spend_cap": 1_000_000.0,
            "merchant_category_scope": ["travel"]
        })
        agent_id = r.json()["agent_id"]
        
        # Start heartbeat
        await client.post(f"{BASE_URL}/agents/{agent_id}/heartbeat/start")
        
        # Give it a wide envelope to avoid dual control or envelope blocks
        await client.patch(f"{BASE_URL}/agents/{agent_id}/policy", json={"k1": 0.01})
        
        # Fire 1 warmup request
        payload = {
            "amount": 100.0,
            "merchant_category": "travel",
            "action_type": "initiate_transfer",
            "action_description": "warmup"
        }
        await client.post(f"{BASE_URL}/agents/{agent_id}/action", json=payload)
        
        print(f"Firing {concurrency} requests concurrently...")
        
        # Fire concurrent requests
        tasks = [fire_request(client, agent_id, payload) for _ in range(concurrency)]
        latencies_raw = await asyncio.gather(*tasks)
        latencies = [l for l in latencies_raw if l is not None]
        failures = len(latencies_raw) - len(latencies)
        
        if not latencies:
            print("All requests failed!")
            return {"n": concurrency, "failed": failures}
            
        latencies.sort()
        
        def p(pct):
            idx = int(len(latencies) * (pct / 100.0))
            if idx >= len(latencies):
                idx = len(latencies) - 1
            return latencies[idx]
            
        p50 = p(50)
        p90 = p(90)
        p99 = p(99)
        avg = sum(latencies) / len(latencies)
        
        print(f"Results for N={concurrency}:")
        print(f"  Failures: {failures} out of {concurrency}")
        print(f"  Average: {avg:.2f} ms")
        print(f"  p50:     {p50:.2f} ms")
        print(f"  p90:     {p90:.2f} ms")
        print(f"  p99:     {p99:.2f} ms")
        
        return {
            "n": concurrency,
            "failed": failures,
            "p50_ms": p50,
            "p90_ms": p90,
            "p99_ms": p99,
            "avg_ms": avg
        }

async def main():
    # 1. Run Accuracy Tests
    passed, total = await run_all_accuracy_tests()
    
    # 2. Run Latency Tests
    results_100 = await run_latency_test(100)
    results_500 = await run_latency_test(500)
    
    # 3. Save combined results
    out_data = {
        "latency": [results_100, results_500],
        "accuracy": {
            "passed": passed,
            "total": total,
            "pass_rate_pct": (passed / total) * 100 if total > 0 else 0
        }
    }
    
    with open("benchmark/results.json", "w") as f:
        json.dump(out_data, f, indent=2)
        
    print(f"Saved results to benchmark/results.json")

if __name__ == "__main__":
    asyncio.run(main())
