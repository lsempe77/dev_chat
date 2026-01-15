"""
Diagnose MineRU Output Quality

This script inspects the raw MineRU output to understand:
1. Are tables being extracted correctly?
2. Are merged headers handled?
3. What does the HTML structure look like?
4. Are there any patterns in failures?
"""

import os
import json
import boto3
from dotenv import load_dotenv
from html.parser import HTMLParser
import re

load_dotenv()

CLOUDFLARE_ACCOUNT_ID = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
R2_BUCKET = os.environ.get('R2_BUCKET_NAME', 'devchat-pdfs')


def get_s3_client():
    """Get R2/S3 client."""
    return boto3.client(
        's3',
        endpoint_url=f'https://{CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY
    )


def load_r2_document(r2_key: str) -> dict:
    """Load JSON document from R2."""
    s3 = get_s3_client()
    response = s3.get_object(Bucket=R2_BUCKET, Key=r2_key)
    content = response['Body'].read()
    try:
        return json.loads(content.decode('utf-8'))
    except UnicodeDecodeError:
        return json.loads(content.decode('latin-1'))


def analyze_table_html(html: str, table_idx: int) -> dict:
    """Analyze HTML table structure."""
    analysis = {
        "table_idx": table_idx,
        "html_length": len(html),
        "has_thead": "<thead" in html.lower(),
        "has_tbody": "<tbody" in html.lower(),
        "has_th": "<th" in html.lower(),
        "has_colspan": "colspan" in html.lower(),
        "has_rowspan": "rowspan" in html.lower(),
        "row_count": html.lower().count("<tr"),
        "cell_count": html.lower().count("<td") + html.lower().count("<th"),
        "issues": []
    }
    
    # Check for common issues
    if analysis["has_colspan"]:
        analysis["issues"].append("MERGED_COLS: Table has colspan (merged columns)")
    if analysis["has_rowspan"]:
        analysis["issues"].append("MERGED_ROWS: Table has rowspan (merged rows)")
    if not analysis["has_th"] and not analysis["has_thead"]:
        analysis["issues"].append("NO_HEADERS: No clear header structure")
    if analysis["row_count"] < 2:
        analysis["issues"].append("TOO_FEW_ROWS: Less than 2 rows")
    
    return analysis


def analyze_document(doc: dict, doc_name: str) -> dict:
    """Analyze a single document's MineRU output."""
    result = {
        "document": doc_name,
        "has_content": bool(doc.get("content")),
        "content_length": len(doc.get("content", "")),
        "has_tables": bool(doc.get("tables")),
        "table_count": len(doc.get("tables", [])),
        "has_formulas": bool(doc.get("formulas")),
        "formula_count": len(doc.get("formulas", [])),
        "tables_analysis": []
    }
    
    # Analyze each table
    for i, table in enumerate(doc.get("tables", [])):
        if isinstance(table, dict):
            html = table.get("table_body", "") or table.get("html", "") or table.get("content", "")
        elif isinstance(table, str):
            html = table
        else:
            html = ""
        
        if html:
            table_analysis = analyze_table_html(html, i)
            result["tables_analysis"].append(table_analysis)
    
    return result


def print_sample_tables(doc: dict, max_tables: int = 3):
    """Print sample tables for visual inspection."""
    tables = doc.get("tables", [])
    
    for i, table in enumerate(tables[:max_tables]):
        print(f"\n{'='*60}")
        print(f"TABLE {i+1}/{len(tables)}")
        print(f"{'='*60}")
        
        if isinstance(table, dict):
            html = table.get("table_body", "") or table.get("html", "") or table.get("content", "")
            # Print any metadata
            for key in table:
                if key not in ["table_body", "html", "content"]:
                    print(f"  {key}: {str(table[key])[:100]}")
        elif isinstance(table, str):
            html = table
        else:
            print("  (Unknown table format)")
            continue
        
        # Print raw HTML (truncated)
        print(f"\nRAW HTML ({len(html)} chars):")
        print("-" * 40)
        print(html[:2000])
        if len(html) > 2000:
            print(f"... (truncated, {len(html) - 2000} more chars)")


def main():
    """Run diagnostic on sample documents."""
    print("=" * 70)
    print("MINERU OUTPUT DIAGNOSTIC")
    print("=" * 70)
    
    # Load matched studies
    with open("evaluation/matched_studies_r2.json", "r") as f:
        studies = json.load(f)
    
    print(f"\nLoaded {len(studies)} studies")
    
    # Analyze first 5 studies in detail
    all_analyses = []
    
    for i, study in enumerate(studies[:10]):
        r2_key = study.get('r2_key')
        author = study.get('ground_truth', {}).get('author', 'Unknown')
        
        if not r2_key:
            print(f"\n[{i+1}] {author}: No R2 key")
            continue
        
        print(f"\n[{i+1}] Loading: {author}")
        print(f"    R2 key: {r2_key}")
        
        try:
            doc = load_r2_document(r2_key)
            analysis = analyze_document(doc, author)
            all_analyses.append(analysis)
            
            print(f"    Content: {analysis['content_length']:,} chars")
            print(f"    Tables: {analysis['table_count']}")
            print(f"    Formulas: {analysis['formula_count']}")
            
            # Show table issues
            for t_analysis in analysis["tables_analysis"][:3]:
                issues = t_analysis["issues"]
                if issues:
                    print(f"    Table {t_analysis['table_idx']}: {', '.join(issues)}")
            
            # Show sample tables for first 2 documents
            if i < 2:
                print_sample_tables(doc, max_tables=2)
                
        except Exception as e:
            print(f"    ERROR: {e}")
    
    # Summary statistics
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    total_tables = sum(a["table_count"] for a in all_analyses)
    tables_with_colspan = 0
    tables_with_rowspan = 0
    tables_no_headers = 0
    
    for a in all_analyses:
        for t in a["tables_analysis"]:
            if any("MERGED_COLS" in issue for issue in t["issues"]):
                tables_with_colspan += 1
            if any("MERGED_ROWS" in issue for issue in t["issues"]):
                tables_with_rowspan += 1
            if any("NO_HEADERS" in issue for issue in t["issues"]):
                tables_no_headers += 1
    
    print(f"Documents analyzed: {len(all_analyses)}")
    print(f"Total tables: {total_tables}")
    print(f"Tables with merged columns: {tables_with_colspan} ({100*tables_with_colspan/max(1,total_tables):.1f}%)")
    print(f"Tables with merged rows: {tables_with_rowspan} ({100*tables_with_rowspan/max(1,total_tables):.1f}%)")
    print(f"Tables without clear headers: {tables_no_headers} ({100*tables_no_headers/max(1,total_tables):.1f}%)")
    
    print("\n" + "=" * 70)
    print("NEXT STEPS")
    print("=" * 70)
    print("1. If many tables have colspan/rowspan → Need header expansion logic")
    print("2. If tables lack headers → Need to infer from first row")
    print("3. If HTML is malformed → Need better parsing/cleanup")


if __name__ == "__main__":
    main()
