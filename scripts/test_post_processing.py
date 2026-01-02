"""
Test Post-Processing Improvements

This script:
1. Fetches a sample document from R2
2. Applies the new post-processing
3. Shows before/after comparison
4. Measures improvement metrics
"""

import sys
sys.path.insert(0, ".")

import json
import boto3
import os
from dotenv import load_dotenv
from src.ingestion.post_processing import post_process_mineru_output, enhance_for_rag

load_dotenv()


def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def list_sample_docs(limit=5):
    """List sample documents from R2."""
    s3 = get_r2_client()
    bucket = os.environ.get("R2_BUCKET_NAME", "devchat-pdfs")
    
    result = s3.list_objects_v2(Bucket=bucket, Prefix="outputs/json/", MaxKeys=limit)
    return [obj["Key"] for obj in result.get("Contents", [])]


def fetch_document(key: str) -> dict:
    """Fetch a document from R2."""
    s3 = get_r2_client()
    bucket = os.environ.get("R2_BUCKET_NAME", "devchat-pdfs")
    
    response = s3.get_object(Bucket=bucket, Key=key)
    return json.loads(response["Body"].read().decode("utf-8"))


def analyze_content(content: str) -> dict:
    """Analyze content for common issues."""
    import re
    
    return {
        "length": len(content),
        "line_count": len(content.split("\n")),
        "reference_sections": len(re.findall(r"(?i)^#{1,3}\s*(?:\d+\.?\s*)?references?\b", content, re.MULTILINE)),
        "page_numbers": len(re.findall(r"^\s*\d{1,4}\s*$", content, re.MULTILINE)),
        "tables": len(re.findall(r"\|[^\n]+\|(?:\n\|[^\n]+\|)+", content)),
        "equations": len(re.findall(r"\$\$[^$]+\$\$", content)),
        "figures": len(re.findall(r"(?i)(?:figure|fig\.?)\s*\d+", content)),
        "ligatures": content.count("ﬁ") + content.count("ﬂ") + content.count("ﬀ"),
        "draft_markers": len(re.findall(r"(?i)\b(?:preprint|draft)\b", content)),
    }


def compare_before_after(doc: dict):
    """Compare document before and after post-processing."""
    raw_content = doc.get("content", "")
    
    # Apply post-processing
    enhanced, stats = post_process_mineru_output(
        raw_markdown=raw_content,
        title=doc.get("title"),
        authors=doc.get("authors"),
        year=doc.get("year"),
        pdf_name=doc.get("source_key", "").split("/")[-1] if doc.get("source_key") else None,
        remove_refs=True,
        add_header=True,
    )
    
    # Analyze both
    before_analysis = analyze_content(raw_content)
    after_analysis = analyze_content(enhanced)
    
    return {
        "doc_id": doc.get("doc_id"),
        "title": doc.get("title", "Unknown")[:60],
        "before": before_analysis,
        "after": after_analysis,
        "stats": stats,
        "raw_sample": raw_content[:500],
        "enhanced_sample": enhanced[:500],
    }


def main():
    print("=" * 70)
    print("POST-PROCESSING COMPARISON TEST")
    print("=" * 70)
    
    # Get sample documents
    print("\nFetching sample documents from R2...")
    doc_keys = list_sample_docs(limit=5)
    
    if not doc_keys:
        print("No documents found in R2!")
        return
    
    print(f"Found {len(doc_keys)} documents")
    
    results = []
    
    for key in doc_keys[:3]:  # Test 3 documents
        print(f"\n{'='*70}")
        print(f"Document: {key}")
        print("=" * 70)
        
        try:
            doc = fetch_document(key)
            comparison = compare_before_after(doc)
            results.append(comparison)
            
            print(f"\nTitle: {comparison['title']}")
            
            print(f"\n📊 BEFORE Post-Processing:")
            for k, v in comparison["before"].items():
                print(f"   {k}: {v}")
            
            print(f"\n✨ AFTER Post-Processing:")
            for k, v in comparison["after"].items():
                before_val = comparison["before"][k]
                diff = v - before_val if isinstance(v, int) else 0
                indicator = "✓" if diff <= 0 else "+"
                print(f"   {k}: {v} ({indicator}{diff})")
            
            print(f"\n🔧 Processing Stats:")
            for k, v in comparison["stats"].items():
                print(f"   {k}: {v}")
            
            print(f"\n📝 Content Sample (first 300 chars):")
            print("-" * 40)
            print("BEFORE:", comparison["raw_sample"][:300].replace("\n", "\\n")[:300])
            print("-" * 40)
            print("AFTER:", comparison["enhanced_sample"][:300].replace("\n", "\\n")[:300])
            
        except Exception as e:
            print(f"Error processing {key}: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    if results:
        total_before_refs = sum(r["before"]["reference_sections"] for r in results)
        total_after_refs = sum(r["after"]["reference_sections"] for r in results)
        
        total_before_pages = sum(r["before"]["page_numbers"] for r in results)
        total_after_pages = sum(r["after"]["page_numbers"] for r in results)
        
        total_before_len = sum(r["before"]["length"] for r in results)
        total_after_len = sum(r["after"]["length"] for r in results)
        
        print(f"\nAcross {len(results)} documents:")
        print(f"  Reference sections: {total_before_refs} -> {total_after_refs} ({'removed' if total_after_refs < total_before_refs else 'same'})")
        print(f"  Page numbers: {total_before_pages} -> {total_after_pages}")
        print(f"  Total content: {total_before_len:,} -> {total_after_len:,} chars")
        print(f"  Reduction: {(1 - total_after_len/total_before_len)*100:.1f}%" if total_before_len > 0 else "N/A")
        
        # Check if improvements were made
        refs_removed = total_before_refs > total_after_refs
        size_reduced = total_after_len < total_before_len
        
        print(f"\n✅ Post-processing {'IS WORKING' if (refs_removed or size_reduced) else 'may need adjustment'}!")
        if refs_removed:
            print(f"   - Reference sections removed: {total_before_refs - total_after_refs}")
        if size_reduced:
            print(f"   - Content cleaned: {total_before_len - total_after_len:,} chars removed")


if __name__ == "__main__":
    main()
