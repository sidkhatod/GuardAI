import asyncio
from uuid import uuid4
import os
import sys

# Add backend directory to sys.path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ledger_service import LedgerService
from app.db import get_pool, close_pool

async def main():
    await get_pool()
    service = LedgerService()
    
    agent_id = None
    
    # Write first event
    print("Writing event 1...")
    res1 = await service.write(agent_id, "TEST_EVENT_1", {"key": "value1"}, "v1.0")
    print(f"Event 1 inserted, prev_hash: {res1['prev_hash']}, entry_hash: {res1['entry_hash']}")
    
    # Write second event
    print("Writing event 2...")
    res2 = await service.write(agent_id, "TEST_EVENT_2", {"key": "value2"}, "v1.0")
    print(f"Event 2 inserted, prev_hash: {res2['prev_hash']}, entry_hash: {res2['entry_hash']}")
    
    # Verify chain
    print("Verifying chain...")
    verify_res = await service.verify_chain()
    print(f"Chain verification: {verify_res}")
    
    await close_pool()

if __name__ == "__main__":
    asyncio.run(main())
