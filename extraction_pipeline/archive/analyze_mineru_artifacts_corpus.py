"""
Analyze MinerU artifacts across multiple documents to find common patterns.
"""
import boto3
import os
import json
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import re
from collections import defaultdict

load_dotenv()

# Connect to R2
account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
r2 = boto3.client(
    's3',
    endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY'),
)

# List all JSON files
paginator = r2.get_paginator('list_objects_v2')
json_keys = []
for page in paginator.paginate(Bucket='devchat-pdfs', Prefix='rags/'):
    for obj in page.get('Contents', []):
        if obj['Key'].endswith('.json') and '/outputs/json/' in obj['Key']:
            json_keys.append(obj['Key'])

print(f"Found {len(json_keys)} processed PDFs")
print("Analyzing first 20 for patterns...\n")

# Aggregate statistics
total_tables = 0
artifact_patterns = defaultdict(int)
figure_as_table = []
empty_tables = []
single_row_tables = []
text_fragments = []
split_tables = []

for key in json_keys[:20]:
    try:
        obj = r2.get_object(Bucket='devchat-pdfs', Key=key)
        doc = json.loads(obj['Body'].read().decode('utf-8'))
        tables = doc.get('tables', [])
        
        study_id = key.split('/')[-1].replace('.json', '')
        
        # Track table numbers for split detection
        table_nums = defaultdict(list)
        
        for i, t in enumerate(tables):
            total_tables += 1
            
            html = t.get('table_body', '')
            caption_list = t.get('table_caption', []) or []
            caption = caption_list[0] if caption_list else ''
            page = t.get('page_idx', -1)
            
            soup = BeautifulSoup(html, 'html.parser') if html else None
            rows = soup.find_all('tr') if soup else []
            row_count = len(rows)
            
            # Pattern 1: Figure extracted as table
            if 'figure' in caption.lower() or 'fig.' in caption.lower() or 'fig ' in caption.lower():
                artifact_patterns['figure_as_table'] += 1
                figure_as_table.append({
                    'study': study_id[:30],
                    'idx': i,
                    'caption': caption[:60],
                    'rows': row_count
                })
            
            # Pattern 2: Empty table body
            if not html or html.strip() == '':
                artifact_patterns['empty_body'] += 1
                empty_tables.append({
                    'study': study_id[:30],
                    'idx': i,
                    'caption': caption[:60] if caption else '[no caption]'
                })
            
            # Pattern 3: Single row (often timeline/diagram)
            elif row_count == 1:
                artifact_patterns['single_row'] += 1
                text = soup.get_text(separator=' ', strip=True) if soup else ''
                single_row_tables.append({
                    'study': study_id[:30],
                    'idx': i,
                    'caption': caption[:40] if caption else '[no caption]',
                    'text': text[:60]
                })
            
            # Pattern 4: Text fragment captured (caption is a sentence with paragraph text)
            if caption and '.' in caption[20:-1] and len(caption) > 80 and row_count <= 2:
                # Check if it looks like inline text reference
                if re.search(r'Table\s+\d+[:\)]\s*\d+\)', caption) or \
                   re.search(r'\(\d+\s+percent', caption.lower()) or \
                   re.search(r'households|women|children', caption.lower()):
                    artifact_patterns['text_fragment'] += 1
                    text_fragments.append({
                        'study': study_id[:30],
                        'idx': i,
                        'caption': caption[:100]
                    })
            
            # Track table numbers for split detection
            match = re.search(r'Table\s*(\d+\.?\d*[a-z]?)', caption, re.IGNORECASE)
            if match:
                table_nums[match.group(1)].append((i, page, row_count, caption[:50]))
        
        # Detect split tables
        for num, entries in table_nums.items():
            if len(entries) > 1:
                # Check if they're on consecutive pages
                pages = [e[1] for e in entries]
                if max(pages) - min(pages) <= 2:  # Within 2 pages
                    artifact_patterns['split_table'] += 1
                    split_tables.append({
                        'study': study_id[:30],
                        'table_num': num,
                        'entries': entries
                    })
                    
    except Exception as e:
        print(f"Error processing {key}: {e}")

# Report
print("=" * 80)
print("MINERU ARTIFACT ANALYSIS ACROSS 20 DOCUMENTS")
print("=" * 80)

print(f"\nTotal tables analyzed: {total_tables}")
print(f"\nArtifact patterns found:")
for pattern, count in sorted(artifact_patterns.items(), key=lambda x: -x[1]):
    pct = 100 * count / total_tables if total_tables else 0
    print(f"  {pattern}: {count} ({pct:.1f}%)")

print(f"\n\n{'=' * 80}")
print("FIGURES EXTRACTED AS TABLES")
print("=" * 80)
for item in figure_as_table[:15]:
    print(f"  [{item['study']}] idx={item['idx']}, rows={item['rows']}: {item['caption']}")

print(f"\n\n{'=' * 80}")
print("EMPTY TABLE BODIES")
print("=" * 80)
for item in empty_tables[:15]:
    print(f"  [{item['study']}] idx={item['idx']}: {item['caption']}")

print(f"\n\n{'=' * 80}")
print("SINGLE ROW TABLES (likely diagrams/timelines)")
print("=" * 80)
for item in single_row_tables[:15]:
    print(f"  [{item['study']}] idx={item['idx']}: {item['caption']}")
    print(f"    Text: {item['text']}")

print(f"\n\n{'=' * 80}")
print("TEXT FRAGMENTS (inline references captured)")
print("=" * 80)
for item in text_fragments[:15]:
    print(f"  [{item['study']}] idx={item['idx']}: {item['caption']}")

print(f"\n\n{'=' * 80}")
print("SPLIT TABLES (same table appearing multiple times)")
print("=" * 80)
for item in split_tables[:15]:
    print(f"  [{item['study']}] Table {item['table_num']}:")
    for idx, page, rows, cap in item['entries']:
        print(f"    idx={idx}, page={page}, rows={rows}: {cap}")
