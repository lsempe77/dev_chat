"""Test the updated classifier on 121378172."""
from extraction_pipeline.batch_classify_v3 import process_single_pdf, get_r2_client

r2 = get_r2_client()

# Process 121378172
json_key = 'rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/076ec917aab5_PDFs_of_included_programs_121378172_Gilligan_(2024).json'
result = process_single_pdf(r2, json_key, verbose=False)

if result['success']:
    df = result['df']
    print('Classification results for 121378172:')
    print()
    for _, row in df.iterrows():
        tn = row['table_number']
        cls = row['classification']
        reason = row['reason']
        print(f'{tn:12} -> {cls:12} ({reason})')
    
    print()
    print('Checking Table A1 and A2 (should be DESCRIPTIVE now):')
    for _, row in df.iterrows():
        if 'A1' in row['table_number'] or 'A2' in row['table_number']:
            print(f"  {row['table_number']}: {row['classification']}")
else:
    print('Error:', result['error'])
