import os
import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://governance:governance_dev@localhost:5432/governance")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=10, max_size=80)
    return _pool

async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
