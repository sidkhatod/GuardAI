import asyncio
import asyncpg
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://governance:governance_dev@localhost:5432/governance")

async def reset_db():
    print(f"Connecting to database: {DATABASE_URL}")
    conn = await asyncpg.connect(DATABASE_URL)
    
    print("Truncating tables...")
    await conn.execute("TRUNCATE TABLE ledger_entries, capability_tokens, agent_dependencies, agents CASCADE;")
    
    print("Resetting sequences...")
    await conn.execute("ALTER SEQUENCE ledger_entries_entry_id_seq RESTART WITH 1;")
    
    print("Database reset successfully.")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(reset_db())
