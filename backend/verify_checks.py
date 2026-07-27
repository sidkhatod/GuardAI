import asyncio
import json
from uuid import uuid4
from fastapi import Request

from app.db import get_pool, close_pool
from app.services.token_service import TokenService, TokenRequest
from app.services.ledger_service import LedgerService

async def main():
    pool = await get_pool()
    token_svc = TokenService()
    ledger_svc = LedgerService()

    # Create test agent manually using raw SQL
    agent_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO agents (agent_id, name, declared_task, declared_intent_vector, base_spend_cap, merchant_category_scope, status, current_epoch)
            VALUES ($1, 'agent-alpha', 'test task', '{0.1, 0.2}', 1000.0, '{"travel"}', 'active', 1)
        """, agent_id)
        
    print(f"Created agent: {agent_id}")

    # 1. Low-risk test request
    low_risk_req = TokenRequest(
        agent_id=agent_id,
        amount=150.0,  # 15% of 1000
        merchant_category="travel",
        action_type="initiate_transfer"
    )
    
    res1 = await token_svc.request_token(low_risk_req)
    print("Low risk request result:", res1['status'])
    
    if res1['status'] == 'allow':
        token_id = res1['token']['token_id']
        async with pool.acquire() as conn:
            token_row = await conn.fetchrow("SELECT * FROM capability_tokens WHERE token_id = $1", token_id)
            print(f"Token in DB: {token_row['token_id']}, combined_and_valid: {token_row['combined_and_valid']}")

    # 2. Wrong merchant_category request
    wrong_category_req = TokenRequest(
        agent_id=agent_id,
        amount=150.0,
        merchant_category="electronics", # Wrong category
        action_type="initiate_transfer"
    )
    
    res2 = await token_svc.request_token(wrong_category_req)
    print("Wrong category request result:", res2['status'])
    print("Reason:", res2.get('reason'))
    
    # 3. Check ledger for action_denied
    async with pool.acquire() as conn:
        ledger_entries = await conn.fetch(
            "SELECT * FROM ledger_entries WHERE agent_id = $1 ORDER BY entry_id DESC LIMIT 2", 
            agent_id
        )
        for entry in ledger_entries:
            print(f"Ledger Entry - Type: {entry['event_type']}")
            if entry['event_type'] == 'action_denied':
                payload = json.loads(entry['payload']) if isinstance(entry['payload'], str) else entry['payload']
                print(f"Ledger Denied Reason: {payload.get('reason')}")

    # 4. Verify chain
    verify_res = await ledger_svc.verify_chain()
    print(f"Ledger verify_chain: {verify_res}")
    
    await close_pool()

if __name__ == "__main__":
    asyncio.run(main())
