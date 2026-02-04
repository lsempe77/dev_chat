"""Investigate low extraction studies to understand why they have few/no rows."""
import os
from dotenv import load_dotenv
load_dotenv()

os.environ['AWS_ACCESS_KEY_ID'] = os.environ.get('R2_ACCESS_KEY_ID', '')
os.environ['AWS_SECRET_ACCESS_KEY'] = os.environ.get('R2_SECRET_ACCESS_KEY', '')

from extraction_pipeline.r2_utils import load_json_by_key, list_all_json_files

# Get the files
files = list_all_json_files()

# Check zero/low extraction studies
low_studies = [
    ('BRAC_Ahmed_2009', '0 rows - has 5 tables'),
    ('BRAC_Jalal_2013', '0 rows - has 3 tables'),
    ('121058370', '1 row'),
    ('121305126', '2 rows'),
    ('BRAC_Haseen_2007', '1 row'),
    ('356305886', '0 rows - no tables'),
    ('Raman_and_Howaida', '0 rows - no tables'),
]

for name, note in low_studies:
    for f in files:
        if f['identifier'] == name or name in f['identifier']:
            print("=" * 70)
            print(f"Study: {f['identifier']}")
            print(f"Note: {note}")
            print(f"File: {f['filename'][:70]}...")
            
            doc = load_json_by_key(f['key'])
            if doc:
                tables = doc.get('tables', [])
                content = doc.get('content', '')
                print(f"Tables in JSON: {len(tables)}")
                print(f"Content length: {len(content)} chars")
                
                # Show tables
                for i, t in enumerate(tables[:5]):
                    html = t.get('html', '')
                    caption = t.get('caption', 'No caption')[:80]
                    print(f"\n  Table {i}: {caption}")
                    print(f"    HTML length: {len(html)} chars")
                    
                    # Check content
                    html_lower = html.lower()
                    has_impact = any(w in html_lower for w in ['impact', 'effect', 'treatment', 'coefficient'])
                    has_numbers = any(c.isdigit() for c in html)
                    has_parens = '(' in html and ')' in html
                    print(f"    Has impact keywords: {has_impact}")
                    print(f"    Has numbers: {has_numbers}, Has parentheses: {has_parens}")
                    
                    # Show first 500 chars of HTML
                    if len(html) > 0:
                        print(f"    Preview: {html[:300]}...")
                
                # If no tables, check content for effect sizes in prose
                if len(tables) == 0 and len(content) > 0:
                    print(f"\n  No tables - checking prose content...")
                    content_lower = content.lower()
                    has_effect = any(w in content_lower for w in ['effect size', 'coefficient', 'standard error', 'p<', 'p ='])
                    print(f"  Has effect keywords in prose: {has_effect}")
                    # Show sample
                    print(f"  Content preview: {content[:500]}...")
            break
    print()
