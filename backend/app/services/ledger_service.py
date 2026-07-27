# WARNING: This file contains the ONLY permitted code path for writing to the ledger_entries table.
# Do not add any other insert paths to this table anywhere else in the project.

import json
import hashlib
from uuid import UUID
from typing import Optional, Dict, Any, List
from app.db import get_pool

class LedgerService:
    async def write(self, agent_id: Optional[UUID], event_type: str, payload: dict, policy_version: str) -> dict:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # 1. Fetch the entry_hash of the most recent row
            row = await conn.fetchrow("SELECT entry_hash FROM ledger_entries ORDER BY entry_id DESC LIMIT 1")
            prev_hash = row["entry_hash"] if row else "GENESIS"

            # 2. Compute entry_hash
            payload_json = json.dumps(payload, sort_keys=True)
            data_to_hash = payload_json + policy_version + prev_hash
            entry_hash = hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()

            # 3. Insert a new row
            insert_query = """
                INSERT INTO ledger_entries (agent_id, event_type, payload, policy_version, prev_hash, entry_hash)
                VALUES ($1, $2, $3::jsonb, $4, $5, $6)
                RETURNING *
            """
            
            # 4. Return the full inserted row as a dict
            inserted_row = await conn.fetchrow(
                insert_query, 
                agent_id, 
                event_type, 
                payload_json, 
                policy_version, 
                prev_hash, 
                entry_hash
            )
            
            row_dict = dict(inserted_row)
            
            # Publish ledger broadcast
            from app.redis_client import get_redis
            import json as json_mod
            r = get_redis()
            
            # Format row_dict for JSON serialization (handle UUID/datetime)
            def _json_serial(obj):
                if isinstance(obj, UUID):
                    return str(obj)
                from datetime import datetime
                if isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Type {type(obj)} not serializable")
                
            await r.publish("ledger_broadcast", json_mod.dumps(row_dict, default=_json_serial))
            
            return row_dict

    async def get_entries(self, limit: int = 100, offset: int = 0) -> List[dict]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM ledger_entries ORDER BY entry_id DESC LIMIT $1 OFFSET $2",
                limit, offset
            )
            return [dict(row) for row in rows]

    async def verify_chain(self) -> dict:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Walk the entire table in entry_id order
            rows = await conn.fetch("SELECT * FROM ledger_entries ORDER BY entry_id ASC")
            
            expected_prev_hash = "GENESIS"
            for row in rows:
                if row["prev_hash"] != expected_prev_hash:
                     return {
                         "valid": False,
                         "first_mismatch_entry_id": row["entry_id"],
                         "expected_hash": expected_prev_hash,
                         "actual_hash": row["prev_hash"]
                     }

                # Recompute hash
                payload_val = row["payload"]
                if isinstance(payload_val, str):
                    payload_dict = json.loads(payload_val)
                else:
                    payload_dict = payload_val

                payload_json = json.dumps(payload_dict, sort_keys=True)
                data_to_hash = payload_json + row["policy_version"] + row["prev_hash"]
                recomputed_hash = hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()
                
                if recomputed_hash != row["entry_hash"]:
                    return {
                        "valid": False,
                        "first_mismatch_entry_id": row["entry_id"],
                        "expected_hash": recomputed_hash,
                        "actual_hash": row["entry_hash"]
                    }
                
                expected_prev_hash = row["entry_hash"]
                
            return {"valid": True}
