#!/usr/bin/env python
"""
Safe Re-Indexing Script with Post-Processing

Re-indexes documents from R2 to a NEW Qdrant collection with enhanced post-processing.
This is SAFE - it creates a new collection and leaves the existing one untouched.

Usage:
    python scripts/safe_reindex_enhanced.py --limit 5  # Test with 5 documents
    python scripts/safe_reindex_enhanced.py --all      # All documents
    python scripts/safe_reindex_enhanced.py --compare  # Compare collections after
"""

import sys
sys.path.insert(0, ".")

import argparse
import json
import os
import time
from typing import Optional

import boto3
import cohere
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance, PayloadSchemaType
import uuid

from src.ingestion.post_processing import post_process_mineru_output
from src.utils.logging import get_logger, setup_logging

load_dotenv()
setup_logging()
logger = get_logger(__name__)

# Configuration
OLD_COLLECTION = "devchat_v2"
NEW_COLLECTION = "devchat_v2_enhanced"
VECTOR_NAME = "dense"
VECTOR_DIM = 1536  # Cohere embed-v4.0
CHUNK_SIZE = 256
CHUNK_OVERLAP = 50


def get_r2_client():
    """Create R2 client."""
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def get_qdrant_client():
    """Create Qdrant client."""
    return QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ["QDRANT_API_KEY"],
    )


def get_cohere_client():
    """Create Cohere client."""
    return cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])


def list_r2_documents(s3, bucket: str, limit: Optional[int] = None) -> list:
    """List all document JSON files in R2."""
    doc_keys = []
    continuation_token = None
    
    while True:
        kwargs = {"Bucket": bucket, "Prefix": "outputs/json/"}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
            
        response = s3.list_objects_v2(**kwargs)
        
        for obj in response.get("Contents", []):
            if obj["Key"].endswith(".json"):
                doc_keys.append(obj["Key"])
                if limit and len(doc_keys) >= limit:
                    return doc_keys
        
        if not response.get("IsTruncated"):
            break
        continuation_token = response.get("NextContinuationToken")
    
    return doc_keys


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list:
    """Simple word-based chunking."""
    words = text.split()
    chunks = []
    
    i = 0
    while i < len(words):
        chunk_words = words[i:i + chunk_size]
        chunk_text = " ".join(chunk_words)
        
        if chunk_text.strip():
            chunks.append({
                "text": chunk_text,
                "word_start": i,
                "word_end": i + len(chunk_words),
            })
        
        i += chunk_size - overlap
        if i >= len(words):
            break
    
    return chunks


def create_enhanced_collection(qdrant: QdrantClient, recreate: bool = False):
    """Create the new enhanced collection."""
    try:
        info = qdrant.get_collection(NEW_COLLECTION)
        if recreate:
            logger.info(f"Deleting existing collection '{NEW_COLLECTION}'...")
            qdrant.delete_collection(NEW_COLLECTION)
            raise Exception("Recreate")
        else:
            logger.info(f"Collection '{NEW_COLLECTION}' already exists with {info.points_count} points")
            return False  # Already exists
    except:
        pass
    
    logger.info(f"Creating new collection '{NEW_COLLECTION}'...")
    qdrant.create_collection(
        collection_name=NEW_COLLECTION,
        vectors_config={
            VECTOR_NAME: VectorParams(size=VECTOR_DIM, distance=Distance.COSINE)
        },
    )
    
    # Create indexes
    for field in ["doc_id", "pdf_name", "title"]:
        try:
            qdrant.create_payload_index(
                collection_name=NEW_COLLECTION,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except:
            pass
    
    logger.info(f"✅ Created collection '{NEW_COLLECTION}'")
    return True


def embed_chunks(cohere_client, chunks: list) -> list:
    """Generate embeddings for chunks."""
    texts = [c["text"] for c in chunks]
    
    # Batch embed (max 96 at a time for Cohere)
    embeddings = []
    for i in range(0, len(texts), 96):
        batch = texts[i:i + 96]
        response = cohere_client.embed(
            texts=batch,
            model="embed-english-v3.0",
            input_type="search_document",
            embedding_types=["float"],
        )
        embeddings.extend([e for e in response.embeddings.float_])
    
    return embeddings


def index_document(
    qdrant: QdrantClient,
    cohere_client,
    content: str,
    metadata: dict,
    doc_id: str,
) -> int:
    """Chunk, embed, and index a single document."""
    # Chunk the content
    chunks = chunk_text(content)
    
    if not chunks:
        logger.warning(f"No chunks created for {doc_id}")
        return 0
    
    # Generate embeddings
    embeddings = embed_chunks(cohere_client, chunks)
    
    # Create points
    points = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        point_id = str(uuid.uuid4())
        payload = {
            "text": chunk["text"],
            "doc_id": doc_id,
            "chunk_index": i,
            **metadata,
        }
        
        points.append(PointStruct(
            id=point_id,
            vector={VECTOR_NAME: embedding},
            payload=payload,
        ))
    
    # Upsert to Qdrant
    qdrant.upsert(collection_name=NEW_COLLECTION, points=points)
    
    return len(points)


def process_document(s3, bucket: str, doc_key: str, qdrant, cohere_client) -> dict:
    """Process a single document: fetch, post-process, embed, index."""
    # Fetch from R2
    response = s3.get_object(Bucket=bucket, Key=doc_key)
    doc_data = json.loads(response["Body"].read().decode("utf-8"))
    
    raw_content = doc_data.get("content", "")
    if not raw_content:
        return {"status": "skip", "reason": "no_content"}
    
    doc_id = doc_data.get("doc_id", doc_key.split("/")[-1].replace(".json", ""))
    
    # Apply post-processing
    enhanced_content, stats = post_process_mineru_output(
        raw_markdown=raw_content,
        title=doc_data.get("title"),
        authors=doc_data.get("authors"),
        year=doc_data.get("year"),
        pdf_name=doc_data.get("source_key", "").split("/")[-1] if doc_data.get("source_key") else None,
    )
    
    # Prepare metadata
    metadata = {
        "title": doc_data.get("title", "Unknown"),
        "authors": doc_data.get("authors"),
        "year": doc_data.get("year"),
        "pdf_name": doc_data.get("source_key", "").split("/")[-1] if doc_data.get("source_key") else None,
        "source": "r2_enhanced",
        "post_processed": True,
    }
    
    # Index the enhanced content
    chunk_count = index_document(qdrant, cohere_client, enhanced_content, metadata, doc_id)
    
    return {
        "status": "success",
        "doc_id": doc_id,
        "title": (doc_data.get("title") or "Unknown")[:50],
        "raw_chars": len(raw_content),
        "enhanced_chars": len(enhanced_content),
        "reduction": stats["length_reduction"],
        "refs_removed": stats["references_removed"],
        "chunks": chunk_count,
    }


def compare_collections(qdrant: QdrantClient):
    """Compare old and new collections."""
    print("\n" + "=" * 70)
    print("COLLECTION COMPARISON")
    print("=" * 70)
    
    try:
        old_info = qdrant.get_collection(OLD_COLLECTION)
        print(f"\n📁 OLD Collection: {OLD_COLLECTION}")
        print(f"   Points: {old_info.points_count:,}")
        print(f"   Vectors: {old_info.vectors_count:,}")
    except Exception as e:
        print(f"\n📁 OLD Collection: {OLD_COLLECTION} - NOT FOUND ({e})")
    
    try:
        new_info = qdrant.get_collection(NEW_COLLECTION)
        print(f"\n📁 NEW Collection: {NEW_COLLECTION}")
        print(f"   Points: {new_info.points_count:,}")
        print(f"   Vectors: {new_info.vectors_count:,}")
    except Exception as e:
        print(f"\n📁 NEW Collection: {NEW_COLLECTION} - NOT FOUND ({e})")
    
    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Safe re-indexing with post-processing")
    parser.add_argument("--limit", type=int, default=5, help="Max documents to process")
    parser.add_argument("--all", action="store_true", help="Process all documents")
    parser.add_argument("--recreate", action="store_true", help="Recreate collection")
    parser.add_argument("--compare", action="store_true", help="Only compare collections")
    
    args = parser.parse_args()
    
    # Initialize clients
    qdrant = get_qdrant_client()
    
    if args.compare:
        compare_collections(qdrant)
        return
    
    s3 = get_r2_client()
    cohere_client = get_cohere_client()
    bucket = os.environ.get("R2_BUCKET_NAME", "devchat-pdfs")
    
    print("=" * 70)
    print("SAFE RE-INDEXING WITH POST-PROCESSING")
    print("=" * 70)
    print(f"\n🔒 OLD collection '{OLD_COLLECTION}' will NOT be modified")
    print(f"📁 NEW collection '{NEW_COLLECTION}' will be created/updated")
    print(f"📊 Limit: {'ALL' if args.all else args.limit} documents")
    print()
    
    # Create new collection
    create_enhanced_collection(qdrant, recreate=args.recreate)
    
    # List documents
    limit = None if args.all else args.limit
    doc_keys = list_r2_documents(s3, bucket, limit=limit)
    print(f"\n📚 Found {len(doc_keys)} documents to process\n")
    
    # Process each document
    results = []
    start_time = time.time()
    
    for i, doc_key in enumerate(doc_keys, 1):
        print(f"[{i}/{len(doc_keys)}] {doc_key.split('/')[-1][:40]}...")
        
        try:
            result = process_document(s3, bucket, doc_key, qdrant, cohere_client)
            results.append(result)
            
            if result["status"] == "success":
                print(f"   ✅ {result['chunks']} chunks, {result['reduction']} reduction" + 
                      (", refs removed" if result["refs_removed"] else ""))
            else:
                print(f"   ⏭️ Skipped: {result['reason']}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            results.append({"status": "error", "error": str(e)})
    
    elapsed = time.time() - start_time
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    successful = [r for r in results if r.get("status") == "success"]
    total_chunks = sum(r.get("chunks", 0) for r in successful)
    
    print(f"\n✅ Documents processed: {len(successful)}/{len(results)}")
    print(f"📦 Total chunks indexed: {total_chunks:,}")
    print(f"⏱️ Time elapsed: {elapsed:.1f}s")
    
    # Compare
    compare_collections(qdrant)
    
    print("\n💡 NEXT STEPS:")
    print("   1. Run evaluation on NEW collection:")
    print(f"      python run_claim_ledger_eval.py --collection {NEW_COLLECTION}")
    print("   2. Compare with OLD collection results")
    print("   3. If improved, migrate to enhanced collection")


if __name__ == "__main__":
    main()
