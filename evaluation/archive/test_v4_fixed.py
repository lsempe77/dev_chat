"""Test fixed V4 on a few studies"""
import os
import json
import pandas as pd
from datetime import datetime
import sys
sys.path.append('evaluation')

# Import after adding to path
from extraction_v4 import load_document_content, extract_study_v4

print("="*70)
print("TESTING FIXED V4 (3 studies)")
print("="*70)

# Load studies
with open("evaluation/matched_studies_r2.json") as f:
    studies = json.load(f)

# Test on first 3 studies
test_studies = studies[:3]
extractions = []

for i, study in enumerate(test_studies):
    study_id = study['study_id']
    print(f"\n[{i+1}/3] Processing study {study_id}...")
    
    content = load_document_content(study)
    if not content:
        print(f"    SKIP: No content")
        continue
    
    print(f"    Content: {len(content):,} chars")
    
    result = extract_study_v4(study_id, content)
    extractions.append(result)
    
    print(f"    ✓ TOTAL: {len(result['outcomes'])} outcomes extracted")

print("\n" + "="*70)
print("SUMMARY")
print("="*70)

total_outcomes = sum(len(e['outcomes']) for e in extractions)
print(f"Studies processed: {len(extractions)}")
print(f"Total outcomes: {total_outcomes}")

for e in extractions:
    passes = e.get('extraction_passes', {})
    print(f"\nStudy {e['study_id']}:")
    print(f"  Pass 1 (general): {passes.get('pass1_general', 0)}")
    print(f"  Pass 2 (tables):  {passes.get('pass2_tables', 0)}")
    print(f"  Pass 3 (category): {passes.get('pass3_category', 0)}")
    print(f"  Before dedup: {passes.get('total_before_dedup', 0)}")
    print(f"  After dedup:  {passes.get('total_after_dedup', 0)}")
    print(f"  Final outcomes: {len(e['outcomes'])}")

if total_outcomes > 0:
    print("\n✅ V4 IS WORKING! The model name fix resolved the issue.")
    print("\nSample outcome from first study:")
    if extractions[0]['outcomes']:
        outcome = extractions[0]['outcomes'][0]
        print(f"  Name: {outcome.get('outcome_name')}")
        print(f"  Category: {outcome.get('outcome_category')}")
        print(f"  Coefficient: {outcome.get('coefficient')}")
        print(f"  SE: {outcome.get('standard_error')}")
else:
    print("\n❌ V4 STILL FAILING - outcomes array is empty after all passes")
