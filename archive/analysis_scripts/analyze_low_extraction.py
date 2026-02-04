"""Analyze table content in low-extraction studies."""
import os
import re
from dotenv import load_dotenv
load_dotenv()
os.environ['AWS_ACCESS_KEY_ID'] = os.environ.get('R2_ACCESS_KEY_ID', '')
os.environ['AWS_SECRET_ACCESS_KEY'] = os.environ.get('R2_SECRET_ACCESS_KEY', '')

from extraction_pipeline.r2_utils import load_json_by_key, list_all_json_files

files = list_all_json_files()

# Check BRAC_Ahmed_2009 table titles
for f in files:
    if 'Ahmed_2009' in f['identifier'] and 'Capability' in f['filename']:
        doc = load_json_by_key(f['key'])
        tables = doc.get('tables', [])
        print('=' * 70)
        print('BRAC_Ahmed_2009 (Capability) - Table titles:')
        for i, t in enumerate(tables):
            body = t.get('table_body', '')
            # Extract table title from first row
            if '<td' in body:
                first_cell = re.search(r'<td[^>]*>([^<]+)</td>', body)
                if first_cell:
                    print(f'  Table {i}: {first_cell.group(1)[:80]}')
        break

print()

# Check BRAC_Jalal_2013 table content 
for f in files:
    if 'Jalal_2013' in f['identifier']:
        doc = load_json_by_key(f['key'])
        tables = doc.get('tables', [])
        print('=' * 70)
        print('BRAC_Jalal_2013 - Detailed table analysis:')
        for i, t in enumerate(tables):
            body = t.get('table_body', '')
            body_lower = body.lower()
            
            # Check for treatment effect indicators
            has_coef = 'coefficient' in body_lower or 'effect' in body_lower or 'impact' in body_lower
            has_se = 'standard error' in body_lower
            has_diff = 'difference' in body_lower or 'diff' in body_lower
            has_program = 'program' in body_lower
            has_control = 'control' in body_lower
            
            print(f'\n  Table {i}:')
            print(f'    Indicators: coef={has_coef}, se={has_se}, diff={has_diff}, program={has_program}, control={has_control}')
            
            # Show first 600 chars
            print(f'    Content preview: {body[:600]}...')
        break

print()

# Check what makes a good extraction study vs bad
print('=' * 70)
print('Comparing good vs problematic study structure:')

# Good study - 121058356 (high extraction)
for f in files:
    if '121058356' in f['identifier']:
        doc = load_json_by_key(f['key'])
        tables = doc.get('tables', [])
        print(f'\n121058356 (good - 711 rows): {len(tables)} tables')
        # Show first table structure
        if tables:
            body = tables[0].get('table_body', '')[:500]
            print(f'  First table preview: {body}...')
        break
