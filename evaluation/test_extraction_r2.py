"""
Extraction Accuracy Test - Using R2 JSON files
Downloads document content from R2 and tests extraction accuracy against ground truth.
"""
import os
import re
import json
import boto3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from dotenv import load_dotenv

load_dotenv()


def get_r2_client():
    """Create R2 client."""
    account_id = os.environ['CLOUDFLARE_ACCOUNT_ID']
    return boto3.client('s3',
        endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        region_name='auto'
    )


def list_json_files(r2, bucket: str, rag_id: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """List all JSON files in R2 and extract study IDs."""
    prefix = f'rags/{rag_id}/outputs/json/'
    
    study_id_to_key = {}
    author_year_to_key = {}  # Fallback: author + year matching
    paginator = r2.get_paginator('list_objects_v2')
    
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get('Contents', []):
            key = obj['Key']
            filename = key.split('/')[-1]
            
            # Extract study ID (12XXXXXXX pattern)
            match = re.search(r'(12[0-9]{7})', key)
            if match:
                study_id = match.group(1)
                study_id_to_key[study_id] = key
            
            # Also extract author + year for fallback matching
            # Pattern: Author_(YYYY) or Author(YYYY)
            author_match = re.search(r'_([A-Za-z]+)[_\(]?\(?(\d{4})\)?\.json', filename)
            if author_match:
                author = author_match.group(1).lower()
                year = author_match.group(2)
                author_year_to_key[f'{author}_{year}'] = key
    
    return study_id_to_key, author_year_to_key


def download_json(r2, bucket: str, key: str) -> dict:
    """Download and parse JSON from R2."""
    resp = r2.get_object(Bucket=bucket, Key=key)
    return json.loads(resp['Body'].read().decode('utf-8'))


def load_ground_truth(path: Path) -> Dict[str, dict]:
    """Load ground truth from exported test dataset."""
    with open(path) as f:
        data = json.load(f)
    return {item['study_id']: item['ground_truth'] for item in data}


def find_matched_studies(ground_truth: Dict[str, dict], r2_files: Dict[str, str], author_year_files: Dict[str, str] = None) -> List[Tuple[str, dict, str]]:
    """Find studies that exist in both ground truth and R2."""
    matched = []
    author_year_files = author_year_files or {}
    
    for study_id, gt in ground_truth.items():
        # First try direct study ID match
        if study_id in r2_files:
            matched.append((study_id, gt, r2_files[study_id]))
        elif author_year_files:
            # Fallback: try author + year matching
            author = gt.get('author', '').split()[0].lower()  # First word of author
            year = str(gt.get('year', ''))
            key = f'{author}_{year}'
            if key in author_year_files:
                matched.append((study_id, gt, author_year_files[key]))
    return matched


def main():
    # Setup
    project_root = Path(__file__).parent.parent
    bucket = os.environ.get('R2_BUCKET_NAME', 'devchat-pdfs')
    rag_id = '0816e8d3-ab23-417c-bf3f-e45531411c73'
    
    print("=== Extraction Accuracy Test ===\n")
    
    # Load ground truth
    gt_path = project_root / 'evaluation' / 'extraction_test_dataset.json'
    ground_truth = load_ground_truth(gt_path)
    print(f"Loaded {len(ground_truth)} studies from ground truth")
    
    # Connect to R2
    r2 = get_r2_client()
    
    # List JSON files in R2 (now returns two dicts)
    r2_files, author_year_files = list_json_files(r2, bucket, rag_id)
    print(f"Found {len(r2_files)} JSON files with study IDs in R2")
    print(f"Found {len(author_year_files)} JSON files with author+year patterns")
    
    # Find matches (using both study ID and author+year fallback)
    matched = find_matched_studies(ground_truth, r2_files, author_year_files)
    print(f"Matched {len(matched)} studies between ground truth and R2\n")
    
    # Show matched studies
    print("Matched studies:")
    for study_id, gt, r2_key in matched[:10]:
        print(f"  {study_id}: {gt['author']} ({gt['country']})")
    
    if len(matched) > 10:
        print(f"  ... and {len(matched) - 10} more")
    
    # Save matched studies for testing
    output = []
    for study_id, gt, r2_key in matched:
        output.append({
            'study_id': study_id,
            'ground_truth': gt,
            'r2_key': r2_key,
        })
    
    output_path = project_root / 'evaluation' / 'matched_studies_r2.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved matched studies to {output_path}")
    
    return matched


if __name__ == '__main__':
    main()
