"""
Knight Capital Demo Controller
Runs two parallel simulations from the same order stream:
  - "no_gov": purely synthetic counter, no checks, climbs to $460M in ~35 seconds
  - "gov":    same orders through the REAL production code path — freezes when governance blocks
"""

import asyncio
import json
import httpx
from typing import Optional

# ── Simulation parameters ─────────────────────────────────────────────────────
TARGET_LOSS        = 460_000_000        # $460M (Knight Capital incident)
DEMO_DURATION_S    = 38                 # "no governance" reaches $460M in this many seconds
BROADCAST_HZ       = 8                 # broadcasts per second
AMOUNT_PER_TICK    = TARGET_LOSS / (DEMO_DURATION_S * BROADCAST_HZ)  # ~$1.5M/tick

# Orders for the "with governance" real-API stream
# Tuned so the first 2-3 pass then governance crushes it
GOV_ORDERS = [
    {"amount": 80_000,      "desc": "Position opening — equity book"},
    {"amount": 180_000,     "desc": "Scale-in order — equity book"},
    {"amount": 420_000,     "desc": "Aggressive scale-in — equity"},
    {"amount": 900_000,     "desc": "Full position escalation"},
    {"amount": 2_000_000,   "desc": "Runaway buy — iteration 5"},
    {"amount": 5_000_000,   "desc": "Runaway buy — iteration 6"},
    {"amount": 10_000_000,  "desc": "Runaway buy — iteration 7"},
]
GOV_ORDER_INTERVAL_S = 3.5   # seconds between real API orders — long enough to be visible

# ── Global state ──────────────────────────────────────────────────────────────
_task:           Optional[asyncio.Task] = None
_running:        bool                   = False
_demo_agent_id:  Optional[str]          = None


async def _register_demo_agent(base_url: str) -> str:
    """Register the rogue demo agent and configure its policy."""
    async with httpx.AsyncClient(timeout=15) as c:
        # Name MUST be "agent-alpha" so Cedar's principal check passes —
        # the governance story is told by ENVELOPE intent-divergence, not Cedar rejection.
        r = await c.post(f"{base_url}/agents", json={
            "name": "agent-alpha",
            "declared_task": "End-of-day reconciliation and position netting across all books",
            "base_spend_cap": 5_000_000.0,
            "merchant_category_scope": ["travel"]   # matches Cedar resource scope
        })
        agent_id = r.json()["agent_id"]

        # Start heartbeat so middleware doesn't block at the first fence
        await c.post(f"{base_url}/agents/{agent_id}/heartbeat/start")

        # k1=3.5: intent_multiplier = exp(-3.5 * ~0.70) ≈ 0.085
        # → effective_cap ≈ $425,000 on first call (from $5M base)
        # Orders 1 ($80K) + 2 ($180K) = $260K  → both PASS (window < cap)
        # Order 3 ($420K) → window $680K > $425K  → DENIED (envelope_exceeded)
        # Pacing: ~2 real orders land in the gov counter before it freezes.
        await c.patch(f"{base_url}/agents/{agent_id}/policy", json={"k1": 3.5, "k2": 4.0})

    return agent_id


async def _run(agent_id: str, base_url: str):
    global _running
    from app.redis_client import get_redis
    r = get_redis()

    no_gov_total = 0.0
    gov_total    = 0.0
    gov_frozen   = False
    gov_freeze_reason = ""
    order_idx    = 0
    last_order_t = asyncio.get_event_loop().time() - GOV_ORDER_INTERVAL_S  # fire first order immediately
    start_t      = asyncio.get_event_loop().time()
    tick_interval = 1.0 / BROADCAST_HZ

    async with httpx.AsyncClient(timeout=10) as http:
        while _running:
            now     = asyncio.get_event_loop().time()
            elapsed = now - start_t

            # ── No-governance: purely synthetic, climbs linearly to $460M ──────
            no_gov_total = min(TARGET_LOSS, AMOUNT_PER_TICK * (elapsed * BROADCAST_HZ))

            # ── With-governance: fire real API orders at controlled cadence ─────
            if (not gov_frozen
                    and order_idx < len(GOV_ORDERS)
                    and (now - last_order_t) >= GOV_ORDER_INTERVAL_S):

                order = GOV_ORDERS[order_idx]
                last_order_t = now
                order_idx   += 1

                try:
                    resp = await http.post(
                        f"{base_url}/agents/{agent_id}/action",
                        json={
                            "amount":               float(order["amount"]),
                            "merchant_category":    "travel",           # matches Cedar resource
                            "action_type":          "initiate_transfer", # matches Cedar action
                            "action_description":   order["desc"]        # diverges from "reconciliation" → k1 kicks in
                        }
                    )
                    result = resp.json()
                    if result.get("status") == "allow":
                        gov_total += order["amount"]
                    else:
                        gov_frozen = True
                        gov_freeze_reason = result.get("reason", "governance_block")
                except Exception as e:
                    gov_frozen = True
                    gov_freeze_reason = str(e)

            # ── Publish broadcast ─────────────────────────────────────────────
            complete = no_gov_total >= TARGET_LOSS
            await r.publish("knight_capital_broadcast", json.dumps({
                "no_gov_total":       no_gov_total,
                "gov_total":          gov_total,
                "gov_frozen":         gov_frozen,
                "gov_freeze_reason":  gov_freeze_reason,
                "elapsed_seconds":    elapsed,
                "complete":           complete,
                "reset":              False
            }))

            if complete:
                _running = False
                break

            await asyncio.sleep(tick_interval)


async def start_demo(base_url: str = "http://localhost:8000") -> dict:
    global _task, _running, _demo_agent_id

    if _running:
        return {"status": "already_running", "agent_id": _demo_agent_id}

    _demo_agent_id = await _register_demo_agent(base_url)
    _running = True
    _task = asyncio.create_task(_run(_demo_agent_id, base_url))

    return {"status": "started", "agent_id": _demo_agent_id}


async def reset_demo() -> dict:
    global _task, _running, _demo_agent_id
    from app.redis_client import get_redis

    _running = False
    if _task:
        _task.cancel()
        _task = None

    r = get_redis()
    await r.publish("knight_capital_broadcast", json.dumps({
        "no_gov_total":      0,
        "gov_total":         0,
        "gov_frozen":        False,
        "gov_freeze_reason": "",
        "elapsed_seconds":   0,
        "complete":          False,
        "reset":             True
    }))

    _demo_agent_id = None
    return {"status": "reset"}
