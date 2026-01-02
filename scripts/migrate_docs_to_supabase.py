"""
Migrate document metadata from Railway PostgreSQL to Supabase.

Run this script locally with environment variables:
- DATABASE_URL: Railway PostgreSQL connection string
- SUPABASE_URL: Supabase project URL
- SUPABASE_SERVICE_KEY: Supabase service role key (not anon key)
- RAG_PROJECT_ID: The UUID of the rag_project in Supabase

Usage:
    python scripts/migrate_docs_to_supabase.py
"""

import os
import asyncio
from datetime import datetime

import asyncpg
from supabase import create_client, Client


async def migrate_documents():
    # Get environment variables
    database_url = os.environ.get("DATABASE_URL")
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
    rag_project_id = os.environ.get("RAG_PROJECT_ID")
    
    if not all([database_url, supabase_url, supabase_key, rag_project_id]):
        print("Missing environment variables!")
        print("Required: DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_KEY, RAG_PROJECT_ID")
        return
    
    # Connect to Railway PostgreSQL
    print("Connecting to Railway PostgreSQL...")
    pg_conn = await asyncpg.connect(database_url)
    
    # Connect to Supabase
    print("Connecting to Supabase...")
    supabase: Client = create_client(supabase_url, supabase_key)
    
    # Fetch documents from Railway PostgreSQL
    print("Fetching documents from Railway PostgreSQL...")
    rows = await pg_conn.fetch("""
        SELECT 
            id,
            title,
            filename,
            authors,
            year,
            abstract,
            item_type,
            doi,
            url,
            journal,
            publisher,
            pages,
            volume,
            issue,
            chunk_count,
            status,
            created_at,
            updated_at
        FROM documents
        ORDER BY created_at
    """)
    
    print(f"Found {len(rows)} documents in Railway PostgreSQL")
    
    # Prepare documents for Supabase
    documents_to_insert = []
    for row in rows:
        # Build metadata JSON
        metadata = {
            "title": row["title"],
            "authors": row["authors"] if row["authors"] else [],
            "year": row["year"],
            "abstract": row["abstract"],
            "item_type": row["item_type"],
            "doi": row["doi"],
            "url": row["url"],
            "journal": row["journal"],
            "publisher": row["publisher"],
            "pages": row["pages"],
            "volume": row["volume"],
            "issue": row["issue"],
        }
        # Remove None values
        metadata = {k: v for k, v in metadata.items() if v is not None}
        
        doc = {
            "rag_project_id": rag_project_id,
            "filename": row["id"],  # Original doc ID becomes filename
            "original_filename": row["filename"] or row["id"],
            "status": "completed" if row["status"] == "indexed" else row["status"] or "completed",
            "r2_input_key": f"input-pdfs/{row['id']}.pdf",
            "metadata": metadata,
            "chunk_count": row["chunk_count"] or 0,
            "created_at": row["created_at"].isoformat() if row["created_at"] else datetime.utcnow().isoformat(),
        }
        documents_to_insert.append(doc)
    
    # Insert into Supabase in batches
    print("Inserting documents into Supabase...")
    batch_size = 50
    inserted = 0
    errors = 0
    
    for i in range(0, len(documents_to_insert), batch_size):
        batch = documents_to_insert[i:i + batch_size]
        try:
            result = supabase.table("documents").insert(batch).execute()
            inserted += len(batch)
            print(f"  Inserted {inserted}/{len(documents_to_insert)}")
        except Exception as e:
            print(f"  Error inserting batch: {e}")
            errors += len(batch)
    
    # Update rag_project stats
    print("Updating RAG project stats...")
    total_chunks = sum(d["chunk_count"] for d in documents_to_insert)
    supabase.table("rag_projects").update({
        "document_count": len(documents_to_insert),
        "chunk_count": total_chunks,
    }).eq("id", rag_project_id).execute()
    
    # Close connections
    await pg_conn.close()
    
    print(f"\nMigration complete!")
    print(f"  Inserted: {inserted}")
    print(f"  Errors: {errors}")
    print(f"  Total chunks: {total_chunks}")


if __name__ == "__main__":
    asyncio.run(migrate_documents())
