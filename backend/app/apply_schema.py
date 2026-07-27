import asyncio
import asyncpg
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://governance:governance_dev@localhost:5432/governance")

async def apply_schema():
    print(f"Connecting to database: {DATABASE_URL}")
    conn = await asyncpg.connect(DATABASE_URL)
    
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r") as f:
        schema_sql = f.read()
        
    print("Applying schema...")
    await conn.execute(schema_sql)
    print("Schema applied successfully.")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(apply_schema())
