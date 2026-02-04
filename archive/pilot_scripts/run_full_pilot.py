"""
Run full extraction pilot on all available studies.
Collects error statistics for analysis.
"""
import os
import re
import sys
import json
import boto3
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extraction_pipeline.pipeline import run_pipeline

# Get all study IDs from R2
def get_study_ids():
    cf_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    client = boto3.client(
        's3',
        endpoint_url=f"https://{cf_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY']
    )
    
    response = client.list_objects_v2(
        Bucket='devchat-pdfs', 
        Prefix='rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/',
        MaxKeys=200
    )
    
    study_ids = []
    for obj in response.get('Contents', []):
        fname = obj['Key'].split('/')[-1]
        match = re.search(r'_(\d{9})(?:_|\.)', fname)
        if match:
            study_ids.append(match.group(1))
    
    return list(set(study_ids))


def run_full_pilot():
    """Run pipeline on all studies and collect statistics."""
    
    study_ids = get_study_ids()
    print(f"=" * 70)
    print(f"FULL PILOT: Running on {len(study_ids)} studies")
    print(f"=" * 70)
    
    # Results collection
    all_results = []
    study_stats = []
    errors = []
    
    for i, study_id in enumerate(sorted(study_ids)):
        print(f"\n[{i+1}/{len(study_ids)}] Processing {study_id}...")
        
        try:
            result = run_pipeline(study_id, use_llm=True, enrich=True)
            
            if result and result[0] is not None:
                df, metadata = result
                
                # Load the saved CSV
                csv_path = f"extraction_pipeline/outputs/{study_id}/extracted_data.csv"
                if os.path.exists(csv_path):
                    df = pd.read_csv(csv_path)
                    df['study_id'] = study_id
                    all_results.append(df)
                    
                    # Collect stats
                    study_stats.append({
                        'study_id': study_id,
                        'rows': len(df),
                        'outcomes': df['outcome_name'].nunique() if 'outcome_name' in df.columns else 0,
                        'tables': df['table_caption'].nunique() if 'table_caption' in df.columns else 0,
                        'coef_coverage': (df['coefficient'].notna().sum() / len(df) * 100) if len(df) > 0 else 0,
                        'se_coverage': (df['standard_error'].notna().sum() / len(df) * 100) if len(df) > 0 else 0,
                        'large_coef_count': len(df[abs(df['coefficient']) > 10]) if 'coefficient' in df.columns else 0,
                    })
                else:
                    study_stats.append({
                        'study_id': study_id,
                        'rows': 0,
                        'outcomes': 0,
                        'tables': 0,
                        'coef_coverage': 0,
                        'se_coverage': 0,
                        'large_coef_count': 0,
                    })
            else:
                study_stats.append({
                    'study_id': study_id,
                    'rows': 0,
                    'outcomes': 0,
                    'tables': 0,
                    'coef_coverage': 0,
                    'se_coverage': 0,
                    'large_coef_count': 0,
                })
                errors.append({'study_id': study_id, 'error': 'No results returned'})
                
        except Exception as e:
            print(f"  ERROR: {e}")
            errors.append({'study_id': study_id, 'error': str(e)})
            study_stats.append({
                'study_id': study_id,
                'rows': 0,
                'outcomes': 0,
                'tables': 0,
                'coef_coverage': 0,
                'se_coverage': 0,
                'large_coef_count': 0,
            })
    
    # Combine all results
    print(f"\n" + "=" * 70)
    print("COMBINING RESULTS")
    print("=" * 70)
    
    if all_results:
        combined_df = pd.concat(all_results, ignore_index=True)
        combined_df.to_csv("extraction_pipeline/outputs/full_pilot_dataset.csv", index=False)
        print(f"Saved combined dataset: {len(combined_df)} total rows")
    
    # Save stats
    stats_df = pd.DataFrame(study_stats)
    stats_df.to_csv("extraction_pipeline/outputs/pilot_study_stats.csv", index=False)
    
    # Save errors
    if errors:
        with open("extraction_pipeline/outputs/pilot_errors.json", 'w') as f:
            json.dump(errors, f, indent=2)
    
    # Print summary
    print(f"\n" + "=" * 70)
    print("PILOT SUMMARY")
    print("=" * 70)
    print(f"Studies processed: {len(study_ids)}")
    print(f"Studies with data: {len([s for s in study_stats if s['rows'] > 0])}")
    print(f"Studies with errors: {len(errors)}")
    print(f"Total rows extracted: {sum(s['rows'] for s in study_stats)}")
    print(f"Total unique outcomes: {combined_df['outcome_name'].nunique() if all_results else 0}")
    
    # Error patterns
    print(f"\nSUSPICIOUS DATA PATTERNS:")
    total_large_coef = sum(s['large_coef_count'] for s in study_stats)
    print(f"  Rows with |coefficient| > 10: {total_large_coef}")
    
    if all_results:
        # Treatment arm analysis
        print(f"\nTREATMENT ARM DISTRIBUTION:")
        arm_counts = combined_df['treatment_arm'].value_counts().head(20)
        for arm, count in arm_counts.items():
            print(f"  {arm}: {count}")
        
        # Flag suspicious arms
        suspicious = ['Test:', 'Mean of', '=', 'p-value', 'p value']
        suspicious_rows = combined_df[combined_df['treatment_arm'].str.contains('|'.join(suspicious), case=False, na=False)]
        print(f"\n  Suspicious treatment arms (contain 'Test:', 'Mean of', etc.): {len(suspicious_rows)} rows")
    
    return combined_df if all_results else None, stats_df, errors


if __name__ == "__main__":
    run_full_pilot()
