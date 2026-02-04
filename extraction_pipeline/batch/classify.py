"""
Batch Table Classification Pipeline v3
Process all PDFs through table classifier and output for human validation.
"""
import boto3
import json
import os
import sys
import pandas as pd
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from extraction_pipeline.classification.classifier_v3 import TableClassifierV3

load_dotenv()


def get_r2_client():
    """Initialize R2 client."""
    account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    return boto3.client(
        's3',
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY'),
    )


def list_all_json_files(r2_client, bucket='devchat-pdfs'):
    """List all MinerU JSON output files in R2."""
    json_files = []
    paginator = r2_client.get_paginator('list_objects_v2')
    
    for page in paginator.paginate(Bucket=bucket, Prefix='rags/'):
        for obj in page.get('Contents', []):
            key = obj['Key']
            # Only get JSON files from outputs/json folder (MinerU parsed files)
            if key.endswith('.json') and '/outputs/json/' in key:
                json_files.append(key)
    
    return json_files


def extract_study_id_from_key(key: str) -> str:
    """Extract study ID from R2 key path."""
    # Key format: rags/{uuid}/outputs/json/{hash}_{folder}_{study_id}.json
    filename = key.split('/')[-1]  # Get filename
    # Extract study ID (last numeric part before .json)
    parts = filename.replace('.json', '').split('_')
    # Find the last numeric part
    for part in reversed(parts):
        if part.isdigit():
            return part
    return filename.replace('.json', '')


def process_single_pdf(r2_client, json_key: str, bucket='devchat-pdfs', verbose=False):
    """Process a single PDF's JSON and return classification results."""
    try:
        # Load document from R2
        obj = r2_client.get_object(Bucket=bucket, Key=json_key)
        doc = json.loads(obj['Body'].read().decode('utf-8'))
        
        # Also fetch markdown for List of Tables cross-reference
        md_key = json_key.replace('/json/', '/md/').replace('.json', '.md')
        try:
            md_obj = r2_client.get_object(Bucket=bucket, Key=md_key)
            md_content = md_obj['Body'].read().decode('utf-8')
        except Exception:
            md_content = ''  # Markdown not available
        
        study_id = extract_study_id_from_key(json_key)
        
        # Run classifier with markdown for LOT cross-reference
        classifier = TableClassifierV3(doc, study_id=study_id, verbose=verbose, md_content=md_content)
        classifier.run_pipeline()
        
        # Get results
        df = classifier.to_dataframe()
        df['study_id'] = study_id
        df['r2_key'] = json_key
        
        summary = classifier.get_classification_summary()
        
        return {
            'success': True,
            'study_id': study_id,
            'df': df,
            'summary': summary,
            'error': None
        }
        
    except Exception as e:
        return {
            'success': False,
            'study_id': extract_study_id_from_key(json_key),
            'df': None,
            'summary': None,
            'error': str(e)
        }


def run_batch_classification(
    output_dir: str = 'extraction_pipeline/outputs',
    max_pdfs: int = None,
    verbose: bool = False
):
    """
    Process all PDFs and generate validation output.
    
    Args:
        output_dir: Directory to save outputs
        max_pdfs: Maximum number of PDFs to process (None = all)
        verbose: Print detailed progress
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print("=" * 80)
    print("TABLE CLASSIFICATION BATCH PIPELINE v3")
    print("=" * 80)
    
    # Connect to R2
    print("\nConnecting to R2...")
    r2 = get_r2_client()
    
    # List all JSON files
    print("Listing processed PDFs...")
    json_files = list_all_json_files(r2)
    print(f"  Found {len(json_files)} processed PDFs")
    
    if max_pdfs:
        json_files = json_files[:max_pdfs]
        print(f"  Processing first {max_pdfs} PDFs")
    
    # Process each PDF
    all_results = []
    all_summaries = []
    errors = []
    
    for i, json_key in enumerate(json_files, 1):
        study_id = extract_study_id_from_key(json_key)
        print(f"\n[{i}/{len(json_files)}] Processing {study_id}...")
        
        result = process_single_pdf(r2, json_key, verbose=verbose)
        
        if result['success']:
            all_results.append(result['df'])
            all_summaries.append({
                'study_id': study_id,
                **result['summary']
            })
            print(f"  [OK] {result['summary']['results']} RESULTS, "
                  f"{result['summary']['descriptive']} DESCRIPTIVE, "
                  f"{result['summary']['skip']} SKIP, "
                  f"{result['summary']['empty']} EMPTY")
        else:
            errors.append({
                'study_id': study_id,
                'r2_key': json_key,
                'error': result['error']
            })
            print(f"  ✗ Error: {result['error'][:80]}...")
    
    # Combine results
    print("\n" + "=" * 80)
    print("SAVING RESULTS")
    print("=" * 80)
    
    # Save all table classifications
    if all_results:
        combined_df = pd.concat(all_results, ignore_index=True)
        
        # Reorder columns for readability
        col_order = [
            'study_id', 'index', 'page', 'table_number', 'caption', 
            'classification', 'confidence', 'reason',
            'has_stars', 'has_se', 'has_pvalue',
            'rows', 'cols', 'section', 'is_continuation', 'r2_key'
        ]
        combined_df = combined_df[[c for c in col_order if c in combined_df.columns]]
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save full CSV
        csv_path = output_path / f'batch_classification_{timestamp}.csv'
        combined_df.to_csv(csv_path, index=False)
        print(f"\n  Full results: {csv_path}")
        print(f"    Total tables: {len(combined_df)}")
        
        # Save summary
        summary_df = pd.DataFrame(all_summaries)
        summary_path = output_path / f'batch_summary_{timestamp}.csv'
        summary_df.to_csv(summary_path, index=False)
        print(f"\n  Summary by study: {summary_path}")
        
        # Create validation-friendly output (RESULTS tables only)
        results_only = combined_df[combined_df['classification'] == 'RESULTS']
        results_path = output_path / f'results_tables_{timestamp}.csv'
        results_only.to_csv(results_path, index=False)
        print(f"\n  RESULTS tables only: {results_path}")
        print(f"    Total RESULTS tables: {len(results_only)}")
        
        # Print overall summary
        print("\n" + "=" * 80)
        print("OVERALL SUMMARY")
        print("=" * 80)
        print(f"  Studies processed: {len(all_summaries)}")
        print(f"  Studies with errors: {len(errors)}")
        print(f"\n  Classification totals:")
        print(f"    RESULTS:     {summary_df['results'].sum():,}")
        print(f"    DESCRIPTIVE: {summary_df['descriptive'].sum():,}")
        print(f"    SKIP:        {summary_df['skip'].sum():,}")
        print(f"    EMPTY:       {summary_df['empty'].sum():,}")
        print(f"    UNKNOWN:     {summary_df['unknown'].sum():,}")
    
    # Save errors
    if errors:
        errors_df = pd.DataFrame(errors)
        errors_path = output_path / f'batch_errors_{timestamp}.csv'
        errors_df.to_csv(errors_path, index=False)
        print(f"\n  Errors: {errors_path}")
    
    return combined_df if all_results else None


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Batch table classification')
    parser.add_argument('--max', type=int, default=None, 
                        help='Max PDFs to process (default: all)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')
    parser.add_argument('--output', '-o', type=str, 
                        default='extraction_pipeline/outputs',
                        help='Output directory')
    
    args = parser.parse_args()
    
    run_batch_classification(
        output_dir=args.output,
        max_pdfs=args.max,
        verbose=args.verbose
    )
