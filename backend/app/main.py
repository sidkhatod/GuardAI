from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from uuid import UUID
import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

from app.db import get_pool, close_pool
from app.services.ledger_service import LedgerService
from app.services.agent_service import AgentService, AgentRegistrationRequest, PolicyUpdateRequest
from app.services.token_service import TokenService, TokenRequest, ApproveSplitAuthRequest
from app.services.heartbeat_service import HeartbeatService
from app.middleware import HeartbeatMiddleware
from pydantic import BaseModel

class TokenResolutionRequest(BaseModel):
    success: bool

from sentence_transformers import SentenceTransformer

import functools
@functools.lru_cache(maxsize=10000)
def cached_encode(model, text):
    return model.encode(text)

@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await get_pool()
    with open("app/schema.sql", "r") as f:
        schema = f.read()
    async with pool.acquire() as conn:
        await conn.execute(schema)
    
    from app.redis_client import get_redis
    r = get_redis()
    global_epoch_raw = await r.get("epoch:global")
    if not global_epoch_raw:
        await r.set("epoch:global", 1)
    
    # Load sentence-transformers model
    model_name = "all-MiniLM-L6-v2"
    from huggingface_hub import constants
    cache_dir = constants.HF_HUB_CACHE
    model_path = os.path.join(cache_dir, f"models--sentence-transformers--{model_name}")
    
    if not os.path.exists(model_path):
        print(f"WARNING: Embedding model '{model_name}' not found in local cache at {model_path}.")
        print("It will be downloaded from the internet now. Ensure internet connectivity!")
        print("For offline demo environments, ensure this model is pre-downloaded ahead of time.")
    
    print("TEMPORARY LOG: Embedding model is loading now. This should only print ONCE.")
    app.state.model = SentenceTransformer(model_name)
    print(f"Model '{model_name}' loaded successfully.")
    
    yield
    
    await close_pool()

app = FastAPI(title="Governance Layer API", lifespan=lifespan)

app.add_middleware(HeartbeatMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/ledger")
async def get_ledger_entries(limit: int = 100, offset: int = 0):
    service = LedgerService()
    return await service.get_entries(limit=limit, offset=offset)

@app.post("/ledger/verify")
async def verify_ledger_chain():
    service = LedgerService()
    return await service.verify_chain()

@app.post("/ledger/simulate-tamper")
async def simulate_tamper(entry_id: int = None):
    from app.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        if entry_id is None:
            row = await conn.fetchrow("SELECT entry_id FROM ledger_entries ORDER BY entry_id DESC LIMIT 1")
            if not row:
                raise HTTPException(status_code=400, detail="Ledger is empty")
            entry_id = row["entry_id"]
        
        # Raw UPDATE bypassing hashing
        await conn.execute("UPDATE ledger_entries SET payload = '{\"tampered\": true}'::jsonb WHERE entry_id = $1", entry_id)
        
    return {"status": "tampered", "entry_id": entry_id}

@app.post("/agents")
async def register_agent(request: Request, data: AgentRegistrationRequest):
    service = AgentService()
    return await service.register_agent(request, data)

@app.get("/agents")
async def list_agents():
    service = AgentService()
    return await service.get_agents()

@app.get("/agents/{agent_id}")
async def get_agent(agent_id: UUID):
    service = AgentService()
    agent = await service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent

@app.patch("/agents/{agent_id}/policy")
async def update_agent_policy(agent_id: UUID, req: PolicyUpdateRequest):
    service = AgentService()
    return await service.update_policy(agent_id, req)

@app.post("/agents/{agent_id}/action")
async def request_action(agent_id: UUID, request: Request, req: TokenRequest):
    model = getattr(request.app.state, "model", None)
    service = TokenService(model=model)
    return await service.request_token(agent_id, req)

@app.post("/agents/{agent_id}/approve-split-auth")
async def approve_split_auth(agent_id: UUID, req: ApproveSplitAuthRequest):
    service = TokenService()
    return await service.approve_split_auth(req)

@app.post("/agents/{agent_id}/action/{token_id}/resolve")
async def resolve_token(agent_id: UUID, token_id: UUID, req: TokenResolutionRequest):
    service = TokenService()
    return await service.resolve_token(agent_id, token_id, req.success)

@app.post("/agents/{agent_id}/heartbeat/start")
async def start_heartbeat(agent_id: UUID):
    HeartbeatService.start_heartbeat(agent_id)
    return {"status": "started", "agent_id": str(agent_id)}

@app.post("/agents/{agent_id}/revoke")
async def revoke_agent(agent_id: UUID):
    await HeartbeatService.revoke_agent(agent_id)
    return {"status": "revoked", "agent_id": str(agent_id)}

@app.post("/fleet/emergency-stop")
async def fleet_emergency_stop():
    await HeartbeatService.fleet_emergency_stop()
    return {"status": "emergency_stop_triggered"}

@app.post("/agents/{agent_id}/re-arm")
async def rearm_agent(agent_id: UUID):
    service = AgentService()
    return await service.rearm_agent(agent_id)

@app.post("/agents/{consumer_id}/depends-on/{producer_id}")
async def create_dependency(consumer_id: UUID, producer_id: UUID):
    # This is a test/demo setup endpoint only
    from app.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO agent_dependencies (consumer_agent_id, producer_agent_id, context_ref) VALUES ($1, $2, 'test_dependency') ON CONFLICT DO NOTHING",
            consumer_id, producer_id
        )
    return {"status": "dependency_created", "consumer": str(consumer_id), "producer": str(producer_id)}

import asyncio
import json

@app.websocket("/ws/fleet")
async def ws_fleet(websocket: WebSocket):
    await websocket.accept()
    from app.redis_client import get_redis
    r = get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(
        "heartbeat_broadcast",
        "revoke_broadcast",
        "effective_cap_broadcast",
        "agent_status_broadcast",
        "pending_approvals",
        "knight_capital_broadcast"
    )
    
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                channel = message["channel"]
                data = message["data"]
                await websocket.send_json({
                    "channel": channel,
                    "payload": json.loads(data)
                })
    except WebSocketDisconnect:
        await pubsub.unsubscribe()

@app.websocket("/ws/ledger")
async def ws_ledger(websocket: WebSocket):
    await websocket.accept()
    from app.redis_client import get_redis
    r = get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe("ledger_broadcast")
    
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                await websocket.send_json({
                    "channel": "ledger_broadcast",
                    "payload": json.loads(data)
                })
    except WebSocketDisconnect:
        await pubsub.unsubscribe()

# ── Knight Capital Demo Endpoints ────────────────────────────────────────────
from app.demo.knight_capital import start_demo, reset_demo

@app.post("/demo/knight-capital/start")
async def demo_start():
    return await start_demo(base_url="http://localhost:8000")

@app.post("/demo/knight-capital/reset")
async def demo_reset():
    return await reset_demo()
