import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect('postgresql://governance:governance_dev@localhost:5432/governance')
    await conn.execute("""UPDATE ledger_entries SET payload = '{"tampered": true}' WHERE entry_id = 2""")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
