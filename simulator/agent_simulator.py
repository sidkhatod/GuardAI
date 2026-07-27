"""
Agent Simulator — Knight Capital Replay Seed
Usage:
    python agent_simulator.py --mode=rogue [--base-url=http://localhost:8000]

In --mode=rogue:
    Registers one agent with a benign-sounding declared_task ("reconciliation"),
    then fires a tight loop of escalating buy-order requests through the real API,
    mirroring Knight Capital's 2012 runaway child-order loop.
"""

import argparse
import asyncio
import httpx
import json

BASE_URL = "http://localhost:8000"

# Escalating order amounts (same sequence used by the demo controller)
ROGUE_ORDER_SEQUENCE = [
    100_000, 250_000, 500_000, 750_000,
    1_000_000, 1_500_000, 2_000_000, 3_000_000,
    5_000_000, 8_000_000, 12_000_000, 20_000_000,
]

async def run_rogue(base_url: str):
    async with httpx.AsyncClient(timeout=30) as client:
        # Register the rogue agent with a benign-sounding declared_task
        print("[ROGUE] Registering agent with benign task: 'reconciliation'")
        resp = await client.post(f"{base_url}/agents", json={
            "name": "recon-service-v2",
            "declared_task": "End-of-day reconciliation and position netting across all books",
            "base_spend_cap": 5_000_000.0,
            "merchant_category_scope": ["reconciliation", "settlement"]
        })
        agent = resp.json()
        agent_id = agent["agent_id"]
        print(f"[ROGUE] Agent registered: {agent_id}")

        # Start heartbeat so middleware doesn't block us immediately
        await client.post(f"{base_url}/agents/{agent_id}/heartbeat/start")
        print("[ROGUE] Heartbeat started")

        # Override k1/k2 for the rogue agent — tuned so governance catches it after ~3 orders
        await client.patch(f"{base_url}/agents/{agent_id}/policy", json={"k1": 3.5, "k2": 4.0})
        print("[ROGUE] Policy set: k1=3.5, k2=4.0")

        # Fire rapid, escalating "buy" orders — the rogue loop
        print("[ROGUE] Firing escalating buy orders (mirroring Knight Capital child-order loop)...")
        for i, amount in enumerate(ROGUE_ORDER_SEQUENCE):
            print(f"[ROGUE] Order #{i+1}: ${amount:,.0f}")
            try:
                r = await client.post(f"{base_url}/agents/{agent_id}/action", json={
                    "amount": float(amount),
                    "merchant_category": "equity_trading",
                    "action_type": "buy_order",
                    "action_description": f"Large equity purchase — escalating position size iteration {i+1}"
                })
                result = r.json()
                status = result.get("status", "unknown")
                reason = result.get("reason", "")
                print(f"         -> {status} {reason}")
                if status == "deny":
                    print(f"[ROGUE] GOVERNANCE HALTED runaway at order #{i+1}: {reason}")
                    print("[ROGUE] Simulation complete.")
                    break
            except Exception as e:
                print(f"[ROGUE] Request error: {e}")

            await asyncio.sleep(0.3)  # tight loop, 300ms between orders

        print(f"[ROGUE] Done. Agent ID: {agent_id}")
        return agent_id


def main():
    parser = argparse.ArgumentParser(description="Agent Simulator — Knight Capital Replay")
    parser.add_argument("--mode", choices=["rogue"], required=True, help="Simulation mode")
    parser.add_argument("--base-url", default=BASE_URL, help="API base URL")
    args = parser.parse_args()

    if args.mode == "rogue":
        asyncio.run(run_rogue(args.base_url))

if __name__ == "__main__":
    main()
