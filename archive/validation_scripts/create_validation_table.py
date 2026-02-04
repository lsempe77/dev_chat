"""
Create a validation table mapping study_id -> PDF filename -> row count
For human ground truth validation
"""
import boto3
import os
import pandas as pd
import re
from dotenv import load_dotenv

load_dotenv()

# Connect to R2
s3 = boto3.client('s3',
    endpoint_url=f'https://{os.getenv("CLOUDFLARE_ACCOUNT_ID")}.r2.cloudflarestorage.com',
    aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
    region_name='auto'
)

bucket = 'devchat-pdfs'
base_prefix = 'rags/0816e8d3-ab23-417c-bf3f-e45531411c73/'

# Get all PDFs to build a mapping
pdf_prefix = base_prefix + 'input-pdfs/'
resp = s3.list_objects_v2(Bucket=bucket, Prefix=pdf_prefix, MaxKeys=1000)

pdf_mapping = {}  # study_id -> pdf_filename
for obj in resp.get('Contents', []):
    key = obj['Key']
    filename = key.replace(pdf_prefix, '')
    if filename and not filename.startswith('.'):
        # Extract study ID from filename
        # Pattern 1: 9-digit numeric ID embedded
        match = re.search(r'(\d{9})', filename)
        if match:
            study_id = match.group(1)
            pdf_mapping[study_id] = filename
        else:
            # Pattern 2: BRAC studies - extract author name
            brac_match = re.search(r'BRAC_programs_\(40\)_(\w+)', filename)
            if brac_match:
                author = brac_match.group(1)
                # Try to match with JSON study IDs
                year_match = re.search(r'_(\d{4})', filename)
                year = year_match.group(1) if year_match else ''
                study_key = f"BRAC_{author}_{year}" if year else f"BRAC_{author}"
                pdf_mapping[study_key] = filename
            else:
                # Other patterns
                pdf_mapping[filename.rsplit('.', 1)[0]] = filename

print(f"Found {len(pdf_mapping)} PDF files mapped")

# Get all JSON files (the actual study IDs we extracted)
json_prefix = base_prefix + 'outputs/json/'
resp = s3.list_objects_v2(Bucket=bucket, Prefix=json_prefix, MaxKeys=1000)

json_study_ids = []
for obj in resp.get('Contents', []):
    key = obj['Key']
    filename = key.replace(json_prefix, '')
    if filename.endswith('.json'):
        study_id = filename.replace('.json', '')
        json_study_ids.append(study_id)

print(f"Found {len(json_study_ids)} JSON files (extracted studies)")

# Load extraction stats
stats_path = 'extraction_pipeline/outputs/full_corpus_all_stats.csv'
if os.path.exists(stats_path):
    stats_df = pd.read_csv(stats_path)
    print(f"Loaded stats for {len(stats_df)} studies")
else:
    print(f"Stats file not found: {stats_path}")
    stats_df = pd.DataFrame()

# Build final table using JSON study IDs as source of truth
validation_data = []

for study_id in sorted(json_study_ids):
    # Find matching PDF
    pdf_name = None
    
    # Try direct match
    if study_id in pdf_mapping:
        pdf_name = pdf_mapping[study_id]
    else:
        # Try to find a PDF containing this study_id
        for key, filename in pdf_mapping.items():
            if study_id in filename or study_id in key:
                pdf_name = filename
                break
    
    # Get extraction stats
    if len(stats_df) > 0:
        match = stats_df[stats_df['study_id'].astype(str) == str(study_id)]
        if len(match) > 0:
            rows = int(match.iloc[0]['rows_extracted'])
            tables = int(match.iloc[0]['tables_processed'])
        else:
            rows = 0
            tables = 0
    else:
        rows = 0
        tables = 0
    
    # Create clean PDF reference for easy finding
    pdf_display = pdf_name if pdf_name else "NOT FOUND"
    
    # Extract readable name from study_id
    if study_id.isdigit():
        readable_name = f"Study {study_id}"
    elif study_id.startswith('BRAC_'):
        parts = study_id.split('_')
        readable_name = f"BRAC - {parts[1]} ({parts[2] if len(parts) > 2 else ''})"
    else:
        readable_name = study_id
    
    validation_data.append({
        'study_id': study_id,
        'readable_name': readable_name,
        'rows_extracted': rows,
        'tables_processed': tables,
        'pdf_filename': pdf_display,
        'validated': '',  # For human to fill
        'accuracy_pct': '',  # For human to fill
        'notes': ''  # For human to fill
    })

# Create DataFrame and sort by rows (highest first for validation priority)
val_df = pd.DataFrame(validation_data)
val_df = val_df.sort_values('rows_extracted', ascending=False)

# Save to CSV
output_path = 'extraction_pipeline/outputs/validation_table.csv'
val_df.to_csv(output_path, index=False)
print(f"\nSaved validation table to: {output_path}")

# Save Excel version for easier human editing
try:
    excel_path = 'extraction_pipeline/outputs/validation_table.xlsx'
    val_df.to_excel(excel_path, index=False)
    print(f"Saved Excel version to: {excel_path}")
except Exception as e:
    print(f"Could not save Excel: {e}")

# Print summary
print(f"\n{'='*80}")
print("VALIDATION TABLE SUMMARY")
print(f"{'='*80}")
print(f"Total studies: {len(val_df)}")
print(f"With data (rows > 0): {len(val_df[val_df['rows_extracted'] > 0])}")
print(f"Without data (rows = 0): {len(val_df[val_df['rows_extracted'] == 0])}")
print(f"Total rows extracted: {val_df['rows_extracted'].sum():,}")

# Print formatted table for top 15
print(f"\n{'='*80}")
print("TOP 15 STUDIES FOR VALIDATION (highest row counts)")
print(f"{'='*80}")
top_df = val_df.head(15)[['study_id', 'readable_name', 'rows_extracted', 'tables_processed']]
print(top_df.to_string(index=False))

# Print zero extraction studies
print(f"\n{'='*80}")
print("ZERO EXTRACTION STUDIES")
print(f"{'='*80}")
zero_df = val_df[val_df['rows_extracted'] == 0][['study_id', 'readable_name']]
if len(zero_df) > 0:
    print(zero_df.to_string(index=False))
else:
    print("None!")
