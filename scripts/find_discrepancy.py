"""Find discrepancies between R2, Qdrant, and PostgreSQL document counts."""
import boto3
import os
from collections import Counter
from dotenv import load_dotenv
from qdrant_client import QdrantClient

load_dotenv()

def main():
    # 1. Get unique doc_ids from Qdrant
    print("=== Checking Qdrant ===")
    qdrant = QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ["QDRANT_API_KEY"],
    )
    
    doc_ids_qdrant = set()
    offset = None
    total_chunks = 0
    while True:
        result = qdrant.scroll("devchat_v2", limit=500, offset=offset, with_payload=["doc_id", "pdf_name"])
        for point in result[0]:
            doc_id = point.payload.get("doc_id") or point.payload.get("pdf_name", "").replace(".pdf", "")
            if doc_id:
                doc_ids_qdrant.add(doc_id)
            total_chunks += 1
        offset = result[1]
        if offset is None:
            break
    
    print(f"  Total chunks: {total_chunks}")
    print(f"  Unique doc_ids: {len(doc_ids_qdrant)}")
    
    # 2. Get PDFs from R2
    print("\n=== Checking R2 ===")
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    bucket = os.environ.get("R2_BUCKET_NAME", "devchat-pdfs")
    
    r2_doc_ids = set()
    continuation_token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": "input-pdfs/"}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        resp = s3.list_objects_v2(**kwargs)
        if "Contents" in resp:
            for obj in resp["Contents"]:
                if obj["Key"].endswith(".pdf"):
                    doc_id = obj["Key"].split("/")[-1].rsplit(".", 1)[0]
                    r2_doc_ids.add(doc_id)
        if resp.get("IsTruncated"):
            continuation_token = resp["NextContinuationToken"]
        else:
            break
    
    print(f"  PDFs in R2: {len(r2_doc_ids)}")
    
    # 3. Get JSON outputs from R2
    json_doc_ids = set()
    continuation_token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": "outputs/json/"}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        resp = s3.list_objects_v2(**kwargs)
        if "Contents" in resp:
            for obj in resp["Contents"]:
                if obj["Key"].endswith(".json"):
                    doc_id = obj["Key"].split("/")[-1].rsplit(".", 1)[0]
                    json_doc_ids.add(doc_id)
        if resp.get("IsTruncated"):
            continuation_token = resp["NextContinuationToken"]
        else:
            break
    
    print(f"  JSON outputs in R2: {len(json_doc_ids)}")
    
    # 4. Find discrepancies
    print("\n=== Discrepancies ===")
    
    # Orphans: in Qdrant but not in R2
    orphans = doc_ids_qdrant - r2_doc_ids
    if orphans:
        print(f"\n❌ Orphans in Qdrant (indexed but no PDF in R2): {len(orphans)}")
        for o in sorted(orphans):
            print(f"    - {o}")
    else:
        print("\n✅ No orphans in Qdrant")
    
    # Missing: in R2 but not in Qdrant
    missing = r2_doc_ids - doc_ids_qdrant
    if missing:
        print(f"\n⚠️ Missing from Qdrant (PDF exists but not indexed): {len(missing)}")
        for m in sorted(missing):
            print(f"    - {m}")
    else:
        print("\n✅ All R2 PDFs are indexed in Qdrant")
    
    # JSON without PDF
    json_orphans = json_doc_ids - r2_doc_ids
    if json_orphans:
        print(f"\n⚠️ JSON outputs without matching PDF: {len(json_orphans)}")
        for j in sorted(json_orphans):
            print(f"    - {j}")


if __name__ == "__main__":
    main()
