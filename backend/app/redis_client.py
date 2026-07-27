# Redis Key Conventions:
#
# spend:window:{agent_id}      -> ZSET, member="{request_id}:{amount}", score=unix_timestamp_ms
# spend:window:fleet            -> ZSET, same structure, all agents combined
# lossratio:{agent_id}:success  -> INTEGER counter
# lossratio:{agent_id}:failure  -> INTEGER counter
# epoch:{agent_id}              -> INTEGER
# epoch:global                  -> INTEGER
# heartbeat:{agent_id}          -> STRING (signed token), TTL = heartbeat_interval * 2
# channel: revoke_broadcast     -> pub/sub, published when any epoch changes
# channel: heartbeat_broadcast  -> pub/sub, published every heartbeat tick

import redis.asyncio as redis

_redis_pool = None

def get_redis():
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool.from_url(
            "redis://localhost:6379", 
            decode_responses=True,
            max_connections=600
        )
    return redis.Redis(connection_pool=_redis_pool)
