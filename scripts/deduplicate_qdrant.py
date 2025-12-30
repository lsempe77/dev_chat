#!/usr/bin/env python
"""
Deduplicate Qdrant collection - remove duplicate chunks.

The Modal pipeline has been adding duplicates instead of upserting properly.
This script keeps only one copy of each (doc_id, chunk_index) pair.
"""

from qdrant_client import QdrantClient
import os
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()

def main():
    c = QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ["QDRANT_API_KEY"],
    )
    
    collection = "devchat_v2"
    
    print("=" * 60)
    print("QDRANT DEDUPLICATION")
    print("=" * 60)
    
    # Step 1: Scan all points and group by (doc_id, chunk_index)
    print("\n[1] Scanning all points...")
    chunk_to_points = defaultdict(list)  # (doc_id, chunk_index) -> [point_ids]
    offset = None
    total = 0
    
    while True:
        pts, offset = c.scroll(collection, limit=1000, offset=offset, with_payload=True)
        if not pts:
            break
        total += len(pts)
        for p in pts:
            key = (p.payload.get("doc_id"), p.payload.get("chunk_index"))
            chunk_to_points[key].append(p.id)
        if offset is None:
            break
        print(f"  Scanned {total} points...", end="\r")
    
    print(f"\n  Total points: {total}")
    print(f"  Unique chunks: {len(chunk_to_points)}")
    
    # Step 2: Find duplicates
    print("\n[2] Finding duplicates...")
    duplicates = {k: v for k, v in chunk_to_points.items() if len(v) > 1}
    duplicate_count = sum(len(v) - 1 for v in duplicates.values())
    
    print(f"  Chunks with duplicates: {len(duplicates)}")
    print(f"  Total duplicate points to remove: {duplicate_count}")
    
    if duplicate_count == 0:
        print("\n✅ No duplicates found!")
        return
    
    # Show worst offenders
    worst = sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True)[:5]
    print("\n  Worst duplicates:")
    for (doc_id, chunk_idx), point_ids in worst:
        print(f"    {doc_id[:30]}... chunk {chunk_idx}: {len(point_ids)} copies")
    
    # Step 3: Confirm deletion
    print(f"\n[3] Will delete {duplicate_count} duplicate points (keeping 1 per chunk)")
    
    # Check for --yes flag
    import sys
    if "--yes" in sys.argv or "-y" in sys.argv:
        confirm = "y"
        print("    Auto-confirmed via --yes flag")
    else:
        confirm = input("    Proceed? [y/N]: ").strip().lower()
    
    if confirm != "y":
        print("    Aborted.")
        return
    
    # Step 4: Delete duplicates (keep first, delete rest)
    print("\n[4] Deleting duplicates...")
    points_to_delete = []
    for point_ids in duplicates.values():
        # Keep the first point, delete the rest
        points_to_delete.extend(point_ids[1:])
    
    # Delete in batches
    batch_size = 1000
    for i in range(0, len(points_to_delete), batch_size):
        batch = points_to_delete[i:i + batch_size]
        c.delete(collection_name=collection, points_selector=batch)
        print(f"  Deleted {min(i + batch_size, len(points_to_delete))}/{len(points_to_delete)}", end="\r")
    
    print(f"\n  ✅ Deleted {len(points_to_delete)} duplicate points")
    
    # Step 5: Verify
    print("\n[5] Verifying...")
    info = c.get_collection(collection)
    print(f"  Points remaining: {info.points_count}")
    print(f"  Expected: {len(chunk_to_points)}")
    
    if info.points_count == len(chunk_to_points):
        print("\n✅ DEDUPLICATION COMPLETE!")
    else:
        print(f"\n⚠️ Point count mismatch - expected {len(chunk_to_points)}, got {info.points_count}")


if __name__ == "__main__":
    main()
