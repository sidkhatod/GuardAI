import asyncio
from uuid import uuid4
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ledger_service import LedgerService
from app.db import get_pool, close_pool

async def main():
    await get_pool()
    service = LedgerService()
    
    agent_id = None
    
    for i in range(1, 5):
        print(f"Writing event {i}...")
        res = await service.write(agent_id, f"EVENT_TYPE_{i}", {"data": f"payload_{i}"}, "v1.0")
        print(f"Inserted entry_id {res['entry_id']}, prev_hash: {res['prev_hash']}, entry_hash: {res['entry_hash']}")
    
    await close_pool()

if __name__ == "__main__":
    asyncio.run(main())
