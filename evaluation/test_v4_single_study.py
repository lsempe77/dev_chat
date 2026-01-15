"""Test V4 on a single study to see why it returns 0 outcomes"""
import json
import sys
sys.path.append('evaluation')
from extraction_v4 import load_document_content, extract_study_v4

# Load studies
with open("evaluation/matched_studies_r2.json") as f:
    studies = json.load(f)

# Test on first study
study = studies[0]
study_id = study['study_id']

print(f"Testing V4 on study {study_id}")
print("=" * 60)

content = load_document_content(study)
if not content:
    print("FAIL: No content loaded")
    sys.exit(1)

print(f"✓ Loaded {len(content)} chars of content")

# Run extraction
result = extract_study_v4(study_id, content)

print("\n" + "=" * 60)
print("RESULT:")
print("=" * 60)
print(f"Metadata fields: {list(result.get('metadata', {}).keys())}")
print(f"Extraction passes: {result.get('extraction_passes', {})}")
print(f"Outcomes extracted: {len(result.get('outcomes', []))}")

if result['outcomes']:
    print("\nFirst outcome:")
    print(json.dumps(result['outcomes'][0], indent=2, default=str))
else:
    print("\n❌ NO OUTCOMES EXTRACTED!")
    print("\nThis is why V4 failed - all passes returned empty outcomes arrays.")
    print("Likely causes:")
    print("  1. Model (Claude Sonnet 4) not following prompt format")
    print("  2. Prompts too complex/verbose")
    print("  3. JSON parsing failing silently")
