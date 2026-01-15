"""Convert V1/V2 results to standard extraction format for comparison"""
import json

def convert_v1_to_standard(v1_data):
    """Convert outcome_extraction.py format to standard format"""
    extractions = []
    
    for result in v1_data['results']:
        extraction = {
            'study_id': result['study_id'],
            'metadata': result.get('ground_truth', {}),  # V1 doesn't extract metadata
            'outcomes': result.get('extracted', {}).get('outcomes', []),
            'extraction_method': 'v1',
            'extraction_timestamp': v1_data.get('timestamp', '')
        }
        extractions.append(extraction)
    
    return {
        'version': 'v1',
        'timestamp': v1_data.get('timestamp', ''),
        'n_studies': len(extractions),
        'extractions': extractions
    }

def convert_v2_to_standard(v2_data):
    """Convert improved_extraction_results.json format to standard format"""
    extractions = []
    
    for result in v2_data['results']:
        extraction = {
            'study_id': result['study_id'],
            'metadata': result.get('ground_truth', {}),  # V2 doesn't extract metadata
            'outcomes': result.get('extracted', {}).get('outcomes', []),
            'extraction_method': 'v2',
            'extraction_timestamp': v2_data.get('timestamp', '')
        }
        extractions.append(extraction)
    
    return {
        'version': 'v2_improved',
        'timestamp': v2_data.get('timestamp', ''),
        'n_studies': len(extractions),
        'extractions': extractions
    }

# Convert V1
print("Converting V1...")
with open('evaluation/outcome_extraction_results.json') as f:
    v1_data = json.load(f)

v1_standard = convert_v1_to_standard(v1_data)

with open('evaluation/v1_extraction_results.json', 'w') as f:
    json.dump(v1_standard, f, indent=2, default=str)

print(f"✓ V1 converted: {len(v1_standard['extractions'])} extractions")

# Convert V2
print("Converting V2...")
with open('evaluation/improved_extraction_results.json') as f:
    v2_data = json.load(f)

v2_standard = convert_v2_to_standard(v2_data)

with open('evaluation/v2_extraction_results.json', 'w') as f:
    json.dump(v2_standard, f, indent=2, default=str)

print(f"✓ V2 converted: {len(v2_standard['extractions'])} extractions")
