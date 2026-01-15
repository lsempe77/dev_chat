#!/usr/bin/env python3
"""Test V6 table extraction."""
from evaluation.extraction_v6_tables import load_document_with_tables
import json

with open('evaluation/matched_studies_r2.json') as f:
    studies = json.load(f)

# Test first 3 studies
for study in studies[:3]:
    content, tables, num = load_document_with_tables(study)
    author = study.get('ground_truth', {}).get('author', 'Unknown')
    print(f'Study: {author}')
    print(f'  Content: {len(content) if content else 0} chars')
    print(f'  Tables: {num}')
    if tables:
        print(f'  First table preview:')
        print(tables[0][:500])
    print()
