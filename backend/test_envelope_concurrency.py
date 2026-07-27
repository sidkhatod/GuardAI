import asyncio
import json
from uuid import uuid4
from app.db import get_pool, close_pool
from app.services.token_service import TokenService, TokenRequest
from app.services.envelope_service import EnvelopeService
from sentence_transformers import SentenceTransformer

async def main():
    print("Loading embedding model...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    print("Loaded embedding model successfully.")
    
    print("1. Registering Agent directly...")
    agent_id = uuid4()
    declared_task = "Pay for corporate travel expenses like flights and hotels"
    declared_intent_vector = model.encode(declared_task).tolist()
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO agents (agent_id, name, declared_task, declared_intent_vector, base_spend_cap, merchant_category_scope, status, current_epoch)
            VALUES ($1, 'rogue-agent', $2, $3, 1000.0, '{"travel", "lodging"}', 'active', 1)
        """, agent_id, declared_task, declared_intent_vector)
    print(f"Registered Agent ID: {agent_id}")
    
    svc = TokenService(model=model)
    env_svc = EnvelopeService()

    print("\n2. Firing 20 rapid requests...")
    on_topic = "book a flight ticket for a business trip"
    off_topic = "buy video games and unauthorized cryptocurrency"
    
    # Do this sequentially to see the cap shrink
    for i in range(20):
        is_good = (i % 2 == 0)
        desc = on_topic if is_good else off_topic
        amt = 10.0 if is_good else 30.0 # Small amounts to avoid hitting 20% high risk rule! (20% of 1000 = 200)
        
        req = TokenRequest(
            amount=amt, merchant_category="travel",
            action_type="initiate_transfer", action_description=desc
        )
        res = await svc.request_token(agent_id, req)
        
        if res["status"] == "allow":
            await svc.resolve_token(res["token"]["token_id"], success=is_good)
            
        # Manually fetch ledger
        async with pool.acquire() as conn:
            last_entry = await conn.fetchrow("SELECT payload FROM ledger_entries WHERE agent_id = $1 ORDER BY entry_id DESC LIMIT 1", agent_id)
        if last_entry:
            payload = json.loads(last_entry["payload"])
            if "envelope_stats" in payload:
                stats = payload["envelope_stats"]
                print(f"Req {i+1:02d} ({'GOOD' if is_good else 'BAD '}) Amt: {amt:04.1f} - Cap: {stats['effective_cap']:.2f}, Div: {stats['divergence_score']:.3f}, LossR: {stats['loss_ratio']:.2f}, Status: {res['status']}")

    print("\n3. Testing Concurrent Burst Atomicity directly against EnvelopeService...")
    # Pre-compute the embedding
    current_action_embedding = model.encode(on_topic).tolist()
    
    burst_reqs = []
    for _ in range(50):
        burst_reqs.append(env_svc.check_envelope(
            agent_id=agent_id,
            base_cap=1000.0,
            declared_intent_vector=declared_intent_vector,
            current_action_embedding=current_action_embedding,
            amount=20.0
        ))
        
    print("Gathering 50 concurrent EnvelopeService.check_envelope requests...")
    burst_responses = await asyncio.gather(*burst_reqs)
    
    allowed_count = 0
    denied_count = 0
    total_allowed_spend = 0.0
    final_cap = 0.0
    final_sum = 0.0
    
    for br in burst_responses:
        if br["allowed"]:
            allowed_count += 1
            total_allowed_spend += 20.0
        else:
            denied_count += 1
        final_cap = br["effective_cap"]
        final_sum = br["current_window_sum"]
            
    print(f"Burst Results: {allowed_count} allowed, {denied_count} denied.")
    print(f"Total allowed spend in burst: {total_allowed_spend:.2f}")
    print(f"Final Effective Cap: {final_cap:.2f}")
    print(f"Final Window Sum: {final_sum:.2f}")
    
    assert final_sum <= final_cap + 20.0, f"Atomicity failure! Window sum {final_sum} exceeds cap {final_cap}."
    
    print("\n4. Verifying Ledger Integrity...")
    from app.services.ledger_service import LedgerService
    ls = LedgerService()
    verify_data = await ls.verify_chain()
    print(f"Ledger Verify Status: {verify_data.get('valid')}")
    
    await close_pool()

if __name__ == "__main__":
    asyncio.run(main())
