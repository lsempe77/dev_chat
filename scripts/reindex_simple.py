"""
Minimal Safe Re-Indexing Script

Re-indexes documents to a new Qdrant collection with post-processing.
ASCII-safe output for Windows terminals.
"""

import sys
sys.path.insert(0, ".")

import json
import os
import uuid
import argparse

import boto3
import cohere
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance

from src.ingestion.post_processing import post_process_mineru_output

load_dotenv()

NEW_COLLECTION = "devchat_v2_enhanced"
OLD_COLLECTION = "devchat_v2"
VECTOR_NAME = "dense"
CHUNK_SIZE = 256


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--recreate", action="store_true")
    args = parser.parse_args()

    # Initialize clients
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    qdrant = QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ["QDRANT_API_KEY"],
    )
    cohere_client = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])
    bucket = os.environ.get("R2_BUCKET_NAME", "devchat-pdfs")

    print("=" * 60)
    print("SAFE RE-INDEXING WITH POST-PROCESSING")
    print("=" * 60)

    # Show old collection info
    try:
        old_info = qdrant.get_collection(OLD_COLLECTION)
        print(f"[OLD] {OLD_COLLECTION}: {old_info.points_count} points (UNTOUCHED)")
    except:
        print(f"[OLD] {OLD_COLLECTION}: not found")

    # Create/recreate new collection
    try:
        if args.recreate:
            qdrant.delete_collection(NEW_COLLECTION)
            print(f"[NEW] Deleted {NEW_COLLECTION}")
            raise Exception("recreate")
        new_info = qdrant.get_collection(NEW_COLLECTION)
        print(f"[NEW] {NEW_COLLECTION}: {new_info.points_count} points (existing)")
    except:
        # Use 1536 for embed-v4.0 (the model used by this project)
        # Check what dimension the old collection uses
        try:
            old_info = qdrant.get_collection(OLD_COLLECTION)
            vectors_config = old_info.config.params.vectors
            if isinstance(vectors_config, dict) and VECTOR_NAME in vectors_config:
                dim = vectors_config[VECTOR_NAME].size
                print(f"[NEW] Using dimension {dim} from old collection")
            else:
                dim = 1536  # Default for embed-v4.0
        except:
            dim = 1536
        
        qdrant.create_collection(
            collection_name=NEW_COLLECTION,
            vectors_config={VECTOR_NAME: VectorParams(size=dim, distance=Distance.COSINE)},
        )
        print(f"[NEW] Created {NEW_COLLECTION} (dim={dim})")

    # List documents
    result = s3.list_objects_v2(Bucket=bucket, Prefix="outputs/json/", MaxKeys=args.limit)
    doc_keys = [obj["Key"] for obj in result.get("Contents", [])]
    print(f"\nProcessing {len(doc_keys)} documents...\n")

    total_chunks = 0

    for i, doc_key in enumerate(doc_keys, 1):
        doc_name = doc_key.split("/")[-1][:30]
        print(f"[{i}/{len(doc_keys)}] {doc_name}", end="... ", flush=True)

        try:
            # Fetch
            response = s3.get_object(Bucket=bucket, Key=doc_key)
            doc_data = json.loads(response["Body"].read().decode("utf-8"))

            raw_content = doc_data.get("content", "")
            if not raw_content:
                print("SKIP (no content)")
                continue

            doc_id = doc_data.get("doc_id", doc_key.split("/")[-1].replace(".json", ""))

            # Post-process
            enhanced, stats = post_process_mineru_output(
                raw_markdown=raw_content,
                title=doc_data.get("title"),
            )

            # Chunk
            words = enhanced.split()
            chunks = []
            idx = 0
            while idx < len(words):
                chunk_text = " ".join(words[idx:idx + CHUNK_SIZE])
                if chunk_text.strip():
                    chunks.append(chunk_text)
                idx += CHUNK_SIZE - 50

            if not chunks:
                print("SKIP (no chunks)")
                continue

            # Embed using embed-v4.0 (1536 dims) to match existing collection
            embeddings = []
            for j in range(0, len(chunks), 96):
                batch = chunks[j:j + 96]
                resp = cohere_client.embed(
                    texts=batch,
                    model="embed-v4.0",
                    input_type="search_document",
                    embedding_types=["float"],
                )
                embeddings.extend([e for e in resp.embeddings.float_])

            # Index
            points = []
            for j, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                points.append(PointStruct(
                    id=str(uuid.uuid4()),
                    vector={VECTOR_NAME: emb},
                    payload={
                        "text": chunk,
                        "doc_id": doc_id,
                        "chunk_index": j,
                        "title": doc_data.get("title", "Unknown"),
                        "post_processed": True,
                    },
                ))

            qdrant.upsert(collection_name=NEW_COLLECTION, points=points)
            total_chunks += len(points)

            refs = "refs removed" if stats.get("references_removed") else ""
            print(f"{len(points)} chunks ({stats.get('length_reduction', 'N/A')}) {refs}")

        except Exception as e:
            print(f"ERROR: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    try:
        old_info = qdrant.get_collection(OLD_COLLECTION)
        print(f"[OLD] {OLD_COLLECTION}: {old_info.points_count} points")
    except:
        pass

    try:
        new_info = qdrant.get_collection(NEW_COLLECTION)
        print(f"[NEW] {NEW_COLLECTION}: {new_info.points_count} points")
    except:
        pass

    print(f"\nTotal chunks indexed this run: {total_chunks}")
    print("\nNEXT: Run evaluation on new collection:")
    print(f"  python run_claim_ledger_eval.py --collection {NEW_COLLECTION}")


if __name__ == "__main__":
    main()
