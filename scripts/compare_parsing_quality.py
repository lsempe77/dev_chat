"""
Compare Parsing Quality: Raw vs Post-Processed

This script fetches existing extracted markdown from R2 and measures
how much the post-processing improves the content quality.

NO RE-INDEXING REQUIRED - just analyzes existing content.
"""

import sys
sys.path.insert(0, ".")

import json
import boto3
import os
import re
from dotenv import load_dotenv
from pathlib import Path
from src.ingestion.post_processing import post_process_mineru_output

load_dotenv()


def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def analyze_parsing_quality(content: str) -> dict:
    """
    Analyze content for parsing quality issues.
    
    Returns dict of metrics - lower is better for most.
    """
    return {
        # Content metrics
        "total_chars": len(content),
        "total_lines": len(content.split("\n")),
        "empty_lines": len([l for l in content.split("\n") if not l.strip()]),
        
        # Issues to remove (lower = better after processing)
        "reference_sections": len(re.findall(
            r"(?i)^#{1,3}\s*(?:\d+\.?\s*)?(?:references?|bibliography)\b", 
            content, re.MULTILINE
        )),
        "page_numbers": len(re.findall(r"^\s*\d{1,4}\s*$", content, re.MULTILINE)),
        "page_of_patterns": len(re.findall(r"(?i)page\s+\d+\s+of\s+\d+", content)),
        "download_notices": len(re.findall(r"(?i)downloaded from", content)),
        "preprint_markers": len(re.findall(r"(?i)\b(?:preprint|draft)\b", content)),
        "ligatures": content.count("ﬁ") + content.count("ﬂ") + content.count("ﬀ"),
        "footnote_markers": len(re.findall(r"\[\d{1,3}\](?!\()", content)),
        
        # Structure (higher = better)
        "tables_count": len(re.findall(r"\|[^\n]+\|(?:\n\|[^\n]+\|)+", content)),
        "headers_count": len(re.findall(r"^#{1,6}\s+\w", content, re.MULTILINE)),
        "figures_mentioned": len(re.findall(r"(?i)(?:figure|fig\.?)\s*\d+", content)),
        
        # Potential issues
        "very_long_lines": len([l for l in content.split("\n") if len(l) > 500]),
        "broken_sentences": len(re.findall(r"\w-\s*\n\s*\w", content)),  # hyphenated across lines
        "garbage_chars": len(re.findall(r"[¬­]+", content)),
    }


def calculate_quality_score(metrics: dict) -> float:
    """
    Calculate overall quality score (0-100, higher = better).
    
    Penalizes issues, rewards good structure.
    """
    score = 100.0
    
    # Penalties for issues (subtract points)
    score -= metrics["reference_sections"] * 10  # References in RAG = bad
    score -= metrics["page_numbers"] * 0.5  # Page numbers = noise
    score -= metrics["page_of_patterns"] * 2
    score -= metrics["download_notices"] * 5
    score -= metrics["preprint_markers"] * 2
    score -= metrics["ligatures"] * 0.1
    score -= metrics["footnote_markers"] * 0.2
    score -= metrics["very_long_lines"] * 1
    score -= metrics["broken_sentences"] * 0.5
    score -= metrics["garbage_chars"] * 0.5
    
    # Bonuses for good structure (add points, capped)
    score += min(metrics["headers_count"] * 2, 10)  # Good headers = good
    score += min(metrics["tables_count"] * 3, 15)   # Tables preserved = good
    
    return max(0, min(100, score))


def compare_document(doc_data: dict) -> dict:
    """Compare a single document before/after post-processing."""
    raw_content = doc_data.get("content", "")
    
    if not raw_content:
        return None
    
    # Analyze raw content
    raw_metrics = analyze_parsing_quality(raw_content)
    raw_score = calculate_quality_score(raw_metrics)
    
    # Apply post-processing
    enhanced, stats = post_process_mineru_output(
        raw_markdown=raw_content,
        title=doc_data.get("title"),
        authors=doc_data.get("authors"),
        year=doc_data.get("year"),
        pdf_name=doc_data.get("source_key", "").split("/")[-1] if doc_data.get("source_key") else None,
    )
    
    # Analyze enhanced content
    enhanced_metrics = analyze_parsing_quality(enhanced)
    enhanced_score = calculate_quality_score(enhanced_metrics)
    
    return {
        "doc_id": doc_data.get("doc_id", "unknown"),
        "title": (doc_data.get("title") or "Unknown")[:60],
        "raw_metrics": raw_metrics,
        "enhanced_metrics": enhanced_metrics,
        "raw_score": raw_score,
        "enhanced_score": enhanced_score,
        "score_improvement": enhanced_score - raw_score,
        "processing_stats": stats,
    }


def main():
    print("=" * 70)
    print("PARSING QUALITY COMPARISON: RAW vs POST-PROCESSED")
    print("=" * 70)
    print("\nThis test compares existing extracted content quality.")
    print("NO RE-INDEXING - just measures potential improvement.\n")
    
    s3 = get_r2_client()
    bucket = os.environ.get("R2_BUCKET_NAME", "devchat-pdfs")
    
    # List documents
    print("Fetching documents from R2...")
    result = s3.list_objects_v2(Bucket=bucket, Prefix="outputs/json/", MaxKeys=10)
    doc_keys = [obj["Key"] for obj in result.get("Contents", [])]
    
    print(f"Found {len(doc_keys)} documents\n")
    
    if not doc_keys:
        print("No documents found!")
        return
    
    comparisons = []
    
    for i, key in enumerate(doc_keys[:5], 1):  # Test 5 documents
        print(f"\n{'='*70}")
        print(f"[{i}/5] {key}")
        print("=" * 70)
        
        try:
            response = s3.get_object(Bucket=bucket, Key=key)
            doc_data = json.loads(response["Body"].read().decode("utf-8"))
            
            comparison = compare_document(doc_data)
            if comparison:
                comparisons.append(comparison)
                
                print(f"Title: {comparison['title']}")
                print(f"\n📊 QUALITY SCORES:")
                print(f"   Raw Score:      {comparison['raw_score']:.1f}/100")
                print(f"   Enhanced Score: {comparison['enhanced_score']:.1f}/100")
                print(f"   Improvement:    +{comparison['score_improvement']:.1f} points")
                
                print(f"\n🔍 KEY CHANGES:")
                raw = comparison['raw_metrics']
                enh = comparison['enhanced_metrics']
                
                changes = [
                    ("Reference sections", raw['reference_sections'], enh['reference_sections']),
                    ("Page numbers", raw['page_numbers'], enh['page_numbers']),
                    ("Footnote markers", raw['footnote_markers'], enh['footnote_markers']),
                    ("Ligatures (OCR)", raw['ligatures'], enh['ligatures']),
                    ("Broken sentences", raw['broken_sentences'], enh['broken_sentences']),
                    ("Download notices", raw['download_notices'], enh['download_notices']),
                ]
                
                for name, before, after in changes:
                    if before != after:
                        print(f"   {name}: {before} -> {after} ({'✓ fixed' if after < before else 'changed'})")
                
                print(f"\n📏 SIZE:")
                print(f"   {raw['total_chars']:,} -> {enh['total_chars']:,} chars ({comparison['processing_stats']['length_reduction']})")
                
        except Exception as e:
            print(f"Error: {e}")
    
    # Summary
    if comparisons:
        print("\n" + "=" * 70)
        print("OVERALL SUMMARY")
        print("=" * 70)
        
        avg_raw = sum(c['raw_score'] for c in comparisons) / len(comparisons)
        avg_enhanced = sum(c['enhanced_score'] for c in comparisons) / len(comparisons)
        avg_improvement = sum(c['score_improvement'] for c in comparisons) / len(comparisons)
        
        total_refs_before = sum(c['raw_metrics']['reference_sections'] for c in comparisons)
        total_refs_after = sum(c['enhanced_metrics']['reference_sections'] for c in comparisons)
        
        total_pages_before = sum(c['raw_metrics']['page_numbers'] for c in comparisons)
        total_pages_after = sum(c['enhanced_metrics']['page_numbers'] for c in comparisons)
        
        print(f"\nAcross {len(comparisons)} documents:")
        print(f"  Average Quality Score: {avg_raw:.1f} -> {avg_enhanced:.1f} (+{avg_improvement:.1f})")
        print(f"  Reference Sections:    {total_refs_before} -> {total_refs_after}")
        print(f"  Page Numbers:          {total_pages_before} -> {total_pages_after}")
        
        print(f"\n{'✅ POST-PROCESSING IMPROVES QUALITY' if avg_improvement > 0 else '⚠️ No improvement detected'}")
        
        if avg_improvement > 0:
            print(f"\n📋 NEXT STEPS TO APPLY IMPROVEMENTS:")
            print("   1. Deploy updated Modal: modal deploy infrastructure/modal_mineru.py")
            print("   2. Create new collection: devchat_v2_enhanced (keeps old data safe)")
            print("   3. Re-process documents with --force-reindex flag")
            print("   4. Run evaluation to measure faithfulness impact")


if __name__ == "__main__":
    main()
