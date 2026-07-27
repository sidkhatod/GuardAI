import math
import numpy as np
import time
from uuid import UUID, uuid4
from app.redis_client import get_redis

# Constants tunable per-agent later
K1 = 2.0
K2 = 3.0
WINDOW_MS = 3600000  # 1 hour sliding window

LUA_SCRIPT = """
-- KEYS[1] = spend:window:{agent_id}
-- ARGV[1] = now_ms, ARGV[2] = window_ms, ARGV[3] = new_amount, ARGV[4] = effective_cap, ARGV[5] = request_id

redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, ARGV[1] - ARGV[2])
local members = redis.call('ZRANGE', KEYS[1], 0, -1)
local total = 0
for _, m in ipairs(members) do
    local amount = tonumber(string.match(m, ":(%d+%.?%d*)$"))
    total = total + amount
end
if total + tonumber(ARGV[3]) > tonumber(ARGV[4]) then
    return {0, total}
else
    redis.call('ZADD', KEYS[1], ARGV[1], ARGV[5] .. ":" .. ARGV[3])
    return {1, total}
end
"""

class EnvelopeService:
    def __init__(self):
        self.r = get_redis()
        # We use a Lua script for atomicity. Without atomicity, concurrent requests
        # from the same agent could race past each other, both reading the same "current total"
        # before either writes, allowing the effective cap to be exceeded. The Lua script
        # runs as a single atomic operation on the Redis server, closing that race condition.
        #
        # We use a sliding-window log (ZSET) instead of a token bucket or leaky bucket:
        # bucket-based rate limiters have a boundary-condition exploit where a burst of traffic
        # timed across a refresh boundary can exceed the intended cap over any given window,
        # which is unacceptable for financial spend enforcement. The ZSET approach drops expired
        # entries and sums exactly what remains, which is mathematically exact.
        self.script = self.r.register_script(LUA_SCRIPT)

    async def check_envelope(self, agent_id: UUID, base_cap: float, declared_intent_vector: list[float], current_action_embedding: list[float], amount: float, k1: float = None, k2: float = None) -> dict:
        # Use per-agent overrides if provided, else fall back to module-level constants
        effective_k1 = k1 if k1 is not None else K1
        effective_k2 = k2 if k2 is not None else K2

        # Compute divergence score
        v1 = np.array(declared_intent_vector)
        v2 = np.array(current_action_embedding)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            cosine_similarity = 0.0
        else:
            cosine_similarity = np.dot(v1, v2) / (norm1 * norm2)
            
        divergence_score = 1.0 - cosine_similarity
        intent_multiplier = math.exp(-effective_k1 * divergence_score)
        
        # Read loss ratio
        successes = await self.r.get(f"lossratio:{agent_id}:success")
        failures = await self.r.get(f"lossratio:{agent_id}:failure")
        successes = int(successes) if successes else 0
        failures = int(failures) if failures else 0
        
        if successes + failures == 0:
            loss_ratio = 0.0
        else:
            loss_ratio = failures / (successes + failures)
            
        loss_ratio_multiplier = math.exp(-effective_k2 * loss_ratio)
        
        # Compute effective_cap
        effective_cap = base_cap * intent_multiplier * loss_ratio_multiplier
        
        # Run lua script
        now_ms = int(time.time() * 1000)
        request_id = str(uuid4())
        keys = [f"spend:window:{agent_id}"]
        args = [now_ms, WINDOW_MS, amount, effective_cap, request_id]
        
        result = await self.script(keys=keys, args=args)
        allowed = result[0] == 1
        current_sum = result[1]
        
        payload = {
            "allowed": allowed,
            "effective_cap": effective_cap,
            "intent_multiplier": intent_multiplier,
            "loss_ratio_multiplier": loss_ratio_multiplier,
            "divergence_score": float(divergence_score),
            "loss_ratio": loss_ratio,
            "current_window_sum": current_sum
        }
        
        import json
        await self.r.publish("effective_cap_broadcast", json.dumps({
            "agent_id": str(agent_id),
            **payload
        }))
        
        return payload
