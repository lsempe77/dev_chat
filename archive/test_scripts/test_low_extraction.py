"""Test extraction on problematic studies."""
import os
from dotenv import load_dotenv
load_dotenv()
os.environ['AWS_ACCESS_KEY_ID'] = os.environ.get('R2_ACCESS_KEY_ID', '')
os.environ['AWS_SECRET_ACCESS_KEY'] = os.environ.get('R2_SECRET_ACCESS_KEY', '')

from extraction_pipeline.r2_utils import load_json_by_key, list_all_json_files
from extraction_pipeline.pipeline import extract_all_tables, classify_table

# Test extraction on studies that had 0/low rows
files = list_all_json_files()

test_studies = [
    'Ahmed_2009',  # Capability - 0 rows
    'Jalal_2013',  # 0 rows  
    '121058370',   # 1 row
]

for study_name in test_studies:
    for f in files:
        if study_name in f['identifier'] or study_name in f['filename']:
            print("=" * 70)
            print(f"Testing: {f['identifier']}")
            doc = load_json_by_key(f['key'])
            if doc:
                tables = doc.get('tables', [])
                print(f"Tables in JSON: {len(tables)}")
                
                # Check each table
                for i, t in enumerate(tables[:5]):
                    body = t.get('table_body', '')
                    caption_list = t.get('table_caption', [])
                    caption = caption_list[0] if caption_list else "No caption"
                    
                    # Classify
                    table_type = classify_table(caption, body, use_llm=False)
                    
                    print(f"\n  Table {i}: {caption[:60]}...")
                    print(f"    Body length: {len(body)} chars")
                    print(f"    Classification: {table_type}")
                    
                    if len(body) > 0:
                        # Show preview
                        print(f"    Preview: {body[:200]}...")
                
                # Run full extraction
                df = extract_all_tables(doc, f['identifier'], use_llm=False)
                print(f"\n  EXTRACTED ROWS: {len(df)}")
                if len(df) > 0:
                    print(df[['outcome_name', 'coefficient', 'standard_error']].head(10))
            break
    print()
