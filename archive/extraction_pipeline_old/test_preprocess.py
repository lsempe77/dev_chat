"""
Test the AutoPK-style preprocessor on real MineRU output.
Compare the quality before and after preprocessing.
"""

import os
import json
import boto3
from dotenv import load_dotenv
from preprocess import preprocess_mineru_table, preprocess_all_tables

load_dotenv()

CLOUDFLARE_ACCOUNT_ID = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
R2_BUCKET = os.environ.get('R2_BUCKET_NAME', 'devchat-pdfs')


def get_s3_client():
    return boto3.client(
        's3',
        endpoint_url=f'https://{CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY
    )


def load_r2_document(r2_key: str) -> dict:
    s3 = get_s3_client()
    response = s3.get_object(Bucket=R2_BUCKET, Key=r2_key)
    content = response['Body'].read()
    try:
        return json.loads(content.decode('utf-8'))
    except UnicodeDecodeError:
        return json.loads(content.decode('latin-1'))


def main():
    print("=" * 70)
    print("TESTING AUTOPK-STYLE PREPROCESSOR ON MINERU OUTPUT")
    print("=" * 70)
    
    # Load matched studies
    with open("evaluation/matched_studies_r2.json", "r") as f:
        studies = json.load(f)
    
    # Test on first 3 studies
    for i, study in enumerate(studies[:3]):
        r2_key = study.get('r2_key')
        author = study.get('ground_truth', {}).get('author', 'Unknown')
        
        if not r2_key:
            continue
        
        print(f"\n{'='*70}")
        print(f"STUDY: {author}")
        print(f"{'='*70}")
        
        doc = load_r2_document(r2_key)
        tables = doc.get("tables", [])
        
        print(f"Total tables in document: {len(tables)}")
        
        # Process first 3 tables
        for j, table in enumerate(tables[:5]):
            print(f"\n{'-'*50}")
            print(f"TABLE {j+1}")
            print(f"{'-'*50}")
            
            # Show raw metadata
            if isinstance(table, dict):
                caption = table.get("table_caption", [])
                footnote = table.get("table_footnote", [])
                print(f"Caption: {caption[:100] if caption else 'None'}")
                print(f"Footnote: {str(footnote)[:100] if footnote else 'None'}")
            
            # Preprocess
            parsed = preprocess_mineru_table(table)
            
            if parsed:
                print(f"\nPREPROCESSED RESULT:")
                print(f"  Headers ({len(parsed.headers)}): {parsed.headers[:4]}...")
                print(f"  Data rows: {len(parsed.rows)}")
                
                # Show first 2 data rows
                for k, row in enumerate(parsed.rows[:2]):
                    print(f"  Row {k}: {row[:4]}...")
                
                # Show markdown output (truncated)
                md = parsed.to_markdown()
                print(f"\nMARKDOWN OUTPUT ({len(md)} chars):")
                print(md[:500])
                if len(md) > 500:
                    print("...")
            else:
                print("  FAILED TO PARSE")
        
        # Summary: compare ground truth outcomes with table content
        gt_outcomes = study.get('ground_truth', {}).get('outcomes', [])
        print(f"\n{'='*50}")
        print(f"GROUND TRUTH OUTCOMES ({len(gt_outcomes)}):")
        for o in gt_outcomes[:5]:
            print(f"  - {o.get('name', 'N/A')[:60]}")
        if len(gt_outcomes) > 5:
            print(f"  ... and {len(gt_outcomes)-5} more")


if __name__ == "__main__":
    main()
