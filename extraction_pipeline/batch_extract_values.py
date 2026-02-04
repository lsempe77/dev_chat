"""
Batch Value Extraction
======================

Extracts coefficient values, SEs, p-values from RESULTS tables identified
by the batch classification pipeline.

Input: results_tables_YYYYMMDD_HHMMSS.csv (from batch_classify_v3.py)
Output: extracted_values_YYYYMMDD_HHMMSS.csv

Usage:
    python batch_extract_values.py                           # Use latest results_tables
    python batch_extract_values.py --input results_tables.csv  # Specific input
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import boto3
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from extraction_pipeline.pipeline import extract_results_table, detect_table_orientation
from extraction_pipeline.pipeline import extract_transposed_table, extract_treatments_in_cols_table
from extraction_pipeline.pipeline import extract_outcomes_in_rows_se_split


def get_r2_client():
    """Create R2 client."""
    account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID') or os.environ.get('R2_ACCOUNT_ID')
    return boto3.client(
        's3',
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
    )


def load_document(r2_client, r2_key: str, bucket='devchat-pdfs') -> dict:
    """Load document JSON from R2."""
    obj = r2_client.get_object(Bucket=bucket, Key=r2_key)
    return json.loads(obj['Body'].read().decode('utf-8'))


def extract_table_by_index(doc: dict, table_index: int, study_id: str) -> list:
    """
    Extract values from a specific table by index.
    
    Returns list of dicts with extracted values.
    """
    tables = doc.get('tables', [])
    
    if table_index >= len(tables):
        return []
    
    table = tables[table_index]
    html = table.get('table_body', '') or table.get('content', '')
    
    if not html:
        return []
    
    # Detect table orientation
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('tr')
    orientation = detect_table_orientation(rows)
    
    # Try extraction based on orientation
    results = []
    
    if orientation == 'rows':
        results = extract_transposed_table(table, study_id)
        if not results:
            results = extract_results_table(table, study_id)
    elif orientation == 'treatments_in_cols':
        results = extract_treatments_in_cols_table(table, study_id)
        if not results:
            results = extract_results_table(table, study_id)
    elif orientation == 'outcomes_in_rows_se_split':
        results = extract_outcomes_in_rows_se_split(table, study_id)
        if not results:
            results = extract_results_table(table, study_id)
    else:
        # Standard column-oriented extraction
        results = extract_results_table(table, study_id)
    
    return results or []


def find_latest_results_csv(output_dir: Path) -> Path:
    """Find the most recent results_tables CSV."""
    csvs = list(output_dir.glob('results_tables_*.csv'))
    if not csvs:
        raise FileNotFoundError("No results_tables_*.csv found in outputs/")
    return max(csvs, key=lambda p: p.stat().st_mtime)


def run_batch_extraction(
    input_csv: Path,
    output_dir: Path,
    max_tables: int = None,
    verbose: bool = False,
):
    """
    Run extraction on all RESULTS tables.
    
    Args:
        input_csv: Path to results_tables CSV
        output_dir: Directory to save outputs
        max_tables: Max tables to process (None = all)
        verbose: Print detailed progress
    """
    print("=" * 80)
    print("BATCH VALUE EXTRACTION")
    print("=" * 80)
    
    # Load results tables
    print(f"\nLoading: {input_csv}")
    results_df = pd.read_csv(input_csv)
    print(f"  Total RESULTS tables: {len(results_df)}")
    print(f"  Unique studies: {results_df['study_id'].nunique()}")
    
    if max_tables:
        results_df = results_df.head(max_tables)
        print(f"  Processing first {max_tables} tables")
    
    # Connect to R2
    print("\nConnecting to R2...")
    r2 = get_r2_client()
    
    # Group by R2 key to avoid re-loading documents
    grouped = results_df.groupby('r2_key')
    print(f"  Documents to load: {len(grouped)}")
    
    # Process each document
    all_extractions = []
    doc_cache = {}  # Cache loaded documents
    
    for r2_key, tables in tqdm(grouped, desc="Processing documents"):
        # Load document (with caching)
        if r2_key not in doc_cache:
            try:
                doc_cache[r2_key] = load_document(r2, r2_key)
            except Exception as e:
                print(f"\n  Error loading {r2_key}: {e}")
                continue
        
        doc = doc_cache[r2_key]
        
        # Extract from each table in this document
        for _, row in tables.iterrows():
            study_id = str(row['study_id'])
            table_index = int(row['index'])
            table_number = row.get('table_number', f'Table {table_index}')
            caption = row.get('caption', '')
            page = row.get('page', -1)
            
            try:
                extracted = extract_table_by_index(doc, table_index, study_id)
                
                if extracted:
                    # Add metadata to each extraction
                    for ext in extracted:
                        ext['study_id'] = study_id
                        ext['table_number'] = table_number
                        ext['table_index'] = table_index
                        ext['page'] = page
                        ext['caption'] = caption
                        ext['r2_key'] = r2_key
                    
                    all_extractions.extend(extracted)
                    
                    if verbose:
                        print(f"  {study_id} {table_number}: {len(extracted)} rows")
                        
            except Exception as e:
                if verbose:
                    print(f"  Error extracting {study_id} table {table_index}: {e}")
    
    # Create output DataFrame
    if not all_extractions:
        print("\n⚠ No values extracted!")
        return
    
    # Convert to DataFrame
    df = pd.DataFrame(all_extractions)
    
    # Reorder columns for readability
    priority_cols = [
        'study_id', 'table_number', 'table_index', 'page',
        'outcome_name', 'coefficient', 'standard_error', 'p_value',
        'significance_stars', 'treatment_arm', 'specification',
    ]
    
    other_cols = [c for c in df.columns if c not in priority_cols]
    col_order = [c for c in priority_cols if c in df.columns] + other_cols
    df = df[col_order]
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_path = output_dir / f'extracted_values_{timestamp}.csv'
    df.to_csv(output_path, index=False)
    
    # Print summary
    print("\n" + "=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)
    print(f"\n  Output: {output_path}")
    print(f"  Total rows extracted: {len(df)}")
    print(f"  Unique studies: {df['study_id'].nunique()}")
    print(f"  Unique tables: {df['table_number'].nunique()}")
    
    # Field coverage
    print("\n  Field coverage:")
    for col in ['coefficient', 'standard_error', 'p_value', 'outcome_name']:
        if col in df.columns:
            non_null = df[col].notna().sum()
            pct = non_null / len(df) * 100
            print(f"    {col}: {non_null}/{len(df)} ({pct:.1f}%)")
    
    return df


def main():
    parser = argparse.ArgumentParser(description='Extract values from RESULTS tables')
    parser.add_argument('--input', type=str, help='Input results_tables CSV (default: latest)')
    parser.add_argument('--output', type=str, default='extraction_pipeline/outputs',
                       help='Output directory')
    parser.add_argument('--max', type=int, help='Max tables to process')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Find input CSV
    if args.input:
        input_csv = Path(args.input)
    else:
        input_csv = find_latest_results_csv(output_dir)
        print(f"Using latest: {input_csv.name}")
    
    if not input_csv.exists():
        print(f"Error: Input file not found: {input_csv}")
        sys.exit(1)
    
    # Run extraction
    run_batch_extraction(
        input_csv=input_csv,
        output_dir=output_dir,
        max_tables=args.max,
        verbose=args.verbose,
    )


if __name__ == '__main__':
    main()
