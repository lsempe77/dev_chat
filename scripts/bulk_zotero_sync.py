"""
Bulk Zotero Sync Script

Syncs all items from a connected Zotero library in batches.
Runs locally without timeout limits.

Usage:
    python scripts/bulk_zotero_sync.py <project_id> [--collection KEY] [--batch-size 50] [--max-items 0]
"""
import argparse
import hashlib
import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

import boto3
from supabase import create_client

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.utils.zotero_client import ZoteroClient


def get_supabase():
    return create_client(
        os.environ['SUPABASE_URL'],
        os.environ['SUPABASE_SERVICE_ROLE_KEY']
    )


def get_r2_client():
    return boto3.client(
        's3',
        endpoint_url=os.environ['R2_ENDPOINT_URL'],
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        region_name='auto'
    )


def sync_batch(
    zotero_client: ZoteroClient,
    supabase,
    r2_client,
    project_id: str,
    collection_key: str = None,
    batch_size: int = 50,
    start: int = 0,
    sync_pdfs: bool = True,
):
    """Sync a batch of items from Zotero."""
    bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
    
    # Get existing documents for matching
    existing_docs = supabase.table("documents").select(
        "id, filename, original_filename, metadata"
    ).eq("rag_project_id", project_id).execute()
    
    # Build lookup maps
    doi_map = {}
    title_map = {}
    zotero_key_map = {}
    for doc in existing_docs.data:
        meta = doc.get("metadata", {}) or {}
        if meta.get("doi"):
            doi_map[meta["doi"].lower().strip()] = doc
        if meta.get("title"):
            title_map[meta["title"].lower().strip()] = doc
        if meta.get("zotero_key"):
            zotero_key_map[meta["zotero_key"]] = doc
    
    # Fetch items
    if collection_key:
        items = zotero_client.zot.collection_items(collection_key, limit=batch_size, start=start)
    else:
        items = zotero_client.zot.top(limit=batch_size, start=start)
    
    if not items:
        return 0, 0, 0, 0, True  # No more items
    
    # Normalize items
    normalized = zotero_client._normalize_items(items)
    
    items_synced = 0
    items_updated = 0
    items_created = 0
    pdfs_downloaded = 0
    
    for item in normalized:
        item_key = item["key"]
        item_title = item.get("title", "")
        item_doi = item.get("doi", "")
        
        # Skip if already synced
        if item_key in zotero_key_map:
            items_synced += 1
            continue
        
        # Check for PDF attachment
        try:
            children = zotero_client.zot.children(item_key)
            has_pdf = any(
                c.get("data", {}).get("contentType") == "application/pdf"
                for c in children
            )
        except Exception:
            has_pdf = False
        
        # Try to match with existing document
        matched_doc = None
        if item_doi:
            matched_doc = doi_map.get(item_doi.lower().strip())
        if not matched_doc and item_title:
            matched_doc = title_map.get(item_title.lower().strip())
        
        if matched_doc:
            # Update metadata
            zotero_metadata = {
                "zotero_key": item_key,
                "zotero_synced_at": datetime.utcnow().isoformat(),
                "item_type": item.get("item_type"),
                "authors": item.get("authors", []),
                "year": item.get("year"),
                "journal": item.get("journal"),
                "abstract": item.get("abstract"),
                "doi": item.get("doi") or matched_doc.get("metadata", {}).get("doi"),
                "url": item.get("url"),
                "metadata_source": "zotero",
                "has_pdf": has_pdf,
            }
            existing_meta = matched_doc.get("metadata", {}) or {}
            merged_meta = {**existing_meta, **zotero_metadata}
            
            supabase.table("documents").update({
                "metadata": merged_meta
            }).eq("id", matched_doc["id"]).execute()
            
            items_updated += 1
            
        elif sync_pdfs and has_pdf:
            # Download PDF
            pdf_result = zotero_client.download_pdf_bytes(item_key)
            
            if pdf_result:
                pdf_bytes, original_filename = pdf_result
                content_hash = hashlib.sha256(pdf_bytes).hexdigest()[:16]
                safe_filename = original_filename.replace(" ", "_").replace("/", "_")
                base_name = os.path.splitext(safe_filename)[0]
                
                doc_id = f"{content_hash}_{base_name}"
                r2_key = f"rags/{project_id}/input-pdfs/{doc_id}.pdf"
                
                # Upload to R2
                r2_client.put_object(
                    Bucket=bucket_name,
                    Key=r2_key,
                    Body=pdf_bytes,
                    ContentType="application/pdf",
                )
                
                # Create document record
                doc_metadata = {
                    "content_hash": content_hash,
                    "zotero_key": item_key,
                    "zotero_synced_at": datetime.utcnow().isoformat(),
                    "title": item.get("title"),
                    "item_type": item.get("item_type"),
                    "authors": item.get("authors", []),
                    "year": item.get("year"),
                    "journal": item.get("journal"),
                    "abstract": item.get("abstract"),
                    "doi": item.get("doi"),
                    "url": item.get("url"),
                    "metadata_source": "zotero",
                    "has_pdf": True,
                }
                
                supabase.table("documents").upsert({
                    "rag_project_id": project_id,
                    "filename": doc_id,
                    "original_filename": original_filename,
                    "file_size_bytes": len(pdf_bytes),
                    "mime_type": "application/pdf",
                    "status": "pending",
                    "r2_input_key": r2_key,
                    "metadata": doc_metadata,
                }, on_conflict="filename,rag_project_id").execute()
                
                pdfs_downloaded += 1
                items_created += 1
        else:
            # Create metadata-only record
            doc_id = f"zotero_{item_key}"
            safe_title = (item.get("title") or "Untitled")[:100].replace(" ", "_").replace("/", "_")
            
            doc_metadata = {
                "zotero_key": item_key,
                "zotero_synced_at": datetime.utcnow().isoformat(),
                "title": item.get("title"),
                "item_type": item.get("item_type"),
                "authors": item.get("authors", []),
                "year": item.get("year"),
                "journal": item.get("journal"),
                "abstract": item.get("abstract"),
                "doi": item.get("doi"),
                "url": item.get("url"),
                "metadata_source": "zotero",
                "has_pdf": False,
            }
            
            try:
                supabase.table("documents").insert({
                    "rag_project_id": project_id,
                    "filename": doc_id,
                    "original_filename": f"{safe_title}.pdf",
                    "file_size_bytes": 0,
                    "mime_type": "application/pdf",
                    "status": "no_pdf",
                    "metadata": doc_metadata,
                }).execute()
                items_created += 1
            except Exception as e:
                if "duplicate" not in str(e).lower():
                    print(f"  Error creating record for {item_title[:50]}: {e}")
        
        items_synced += 1
    
    done = len(items) < batch_size
    return items_synced, items_updated, items_created, pdfs_downloaded, done


def main():
    parser = argparse.ArgumentParser(description="Bulk sync Zotero library to RAG project")
    parser.add_argument("project_id", help="RAG project ID")
    parser.add_argument("--collection", help="Zotero collection key (optional)")
    parser.add_argument("--batch-size", type=int, default=50, help="Items per batch (default: 50)")
    parser.add_argument("--max-items", type=int, default=0, help="Max items to sync (0 = all)")
    parser.add_argument("--no-pdfs", action="store_true", help="Don't download PDFs")
    args = parser.parse_args()
    
    supabase = get_supabase()
    r2_client = get_r2_client()
    
    # Get Zotero connection
    connection = supabase.table("zotero_connections").select("*").eq(
        "rag_project_id", args.project_id
    ).execute()
    
    if not connection.data:
        print(f"Error: No Zotero connection found for project {args.project_id}")
        print("Please connect Zotero via the web UI first.")
        sys.exit(1)
    
    conn = connection.data[0]
    print(f"Connected to Zotero library: {conn['library_type']} / {conn['zotero_user_id']}")
    
    zotero_client = ZoteroClient(
        conn["api_key"],
        conn["zotero_user_id"],
        conn["library_type"]
    )
    
    # Get total items
    total_items = zotero_client.zot.num_items()
    print(f"Total items in Zotero: {total_items}")
    
    if args.max_items > 0:
        total_items = min(total_items, args.max_items)
        print(f"Will sync up to {total_items} items")
    
    # Sync in batches
    start = 0
    total_synced = 0
    total_updated = 0
    total_created = 0
    total_pdfs = 0
    
    print(f"\nStarting sync (batch size: {args.batch_size})...")
    print("-" * 60)
    
    while True:
        print(f"Batch {start // args.batch_size + 1}: items {start}-{start + args.batch_size}...", end=" ", flush=True)
        
        synced, updated, created, pdfs, done = sync_batch(
            zotero_client,
            supabase,
            r2_client,
            args.project_id,
            collection_key=args.collection,
            batch_size=args.batch_size,
            start=start,
            sync_pdfs=not args.no_pdfs,
        )
        
        total_synced += synced
        total_updated += updated
        total_created += created
        total_pdfs += pdfs
        
        print(f"synced={synced}, updated={updated}, created={created}, pdfs={pdfs}")
        
        if done or (args.max_items > 0 and total_synced >= args.max_items):
            break
        
        start += args.batch_size
        time.sleep(1)  # Rate limiting
    
    print("-" * 60)
    print(f"\nSync complete!")
    print(f"  Total synced: {total_synced}")
    print(f"  Updated existing: {total_updated}")
    print(f"  Created new: {total_created}")
    print(f"  PDFs downloaded: {total_pdfs}")
    
    # Update connection metadata
    supabase.table("zotero_connections").update({
        "last_synced_at": datetime.utcnow().isoformat(),
        "total_items_synced": total_synced,
        "last_sync_error": None,
    }).eq("id", conn["id"]).execute()


if __name__ == "__main__":
    main()
