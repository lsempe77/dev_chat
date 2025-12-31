import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy import text
from src.database.connection import get_db_context, init_database

load_dotenv()

async def check_postgres():
    print("Connecting to PostgreSQL...")
    init_database()
    try:
        async with get_db_context() as db:
            # Count total documents
            result = await db.execute(text("SELECT COUNT(*) FROM documents"))
            count = result.scalar()
            print(f"Total documents in Postgres: {count}")
            
            # List recent documents (last 20)
            print("\nMost recent 20 documents:")
            result = await db.execute(text("SELECT id, filename, status, created_at FROM documents ORDER BY created_at DESC LIMIT 20"))
            rows = result.fetchall()
            for row in rows:
                print(f"  - {row[0]} | {row[1]} | {row[2]} | {row[3]}")
                
            # Check for specific missing files if known
            # The user mentioned 12 files, e.g. 11aa6d14_121294813
            print("\nChecking for specific 'missing' files:")
            missing_examples = [
                "11aa6d14_121294813",
                "18c72c7b_121058368",
                "2facbce1_121498842_Spanish"
            ]
            for doc_id in missing_examples:
                # Try exact match or like
                res = await db.execute(text(f"SELECT id, status FROM documents WHERE id LIKE '%{doc_id}%'"))
                found = res.fetchone()
                if found:
                    print(f"  ✅ Found {doc_id}: {found}")
                else:
                    print(f"  ❌ Missing {doc_id}")

    except Exception as e:
        print(f"Error connecting to Postgres: {e}")

if __name__ == "__main__":
    asyncio.run(check_postgres())
