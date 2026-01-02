"""List tables in Railway PostgreSQL."""
import asyncio
import os
import asyncpg

async def main():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    rows = await conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )
    print("Tables in Railway PostgreSQL:")
    for row in rows:
        print(f"  - {row['table_name']}")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
