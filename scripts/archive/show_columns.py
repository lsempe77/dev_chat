"""Show columns of documents table."""
import asyncio
import os
import asyncpg

async def main():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    rows = await conn.fetch("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'documents'
        ORDER BY ordinal_position
    """)
    print("Columns in 'documents' table:")
    for row in rows:
        print(f"  - {row['column_name']}: {row['data_type']}")
    
    # Also get a sample row
    sample = await conn.fetchrow("SELECT * FROM documents LIMIT 1")
    if sample:
        print("\nSample row keys:", list(sample.keys()))
    
    # Count
    count = await conn.fetchval("SELECT COUNT(*) FROM documents")
    print(f"\nTotal documents: {count}")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
