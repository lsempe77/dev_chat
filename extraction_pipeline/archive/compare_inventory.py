"""Compare inventory vs extracted to find false positives and negatives."""
import pandas as pd

# Load inventory and extracted
inventory = pd.read_csv('extraction_pipeline/outputs/all_tables_inventory.csv')
extracted = pd.read_csv('extraction_pipeline/outputs/full_corpus_for_validation.csv')

print('COMPARISON: Inventory vs Extracted')
print('=' * 80)
print(f'Total tables in documents: {len(inventory)}')
print(f'  - likely_results: {len(inventory[inventory["likely_type"]=="likely_results"])}')
print(f'  - likely_descriptive: {len(inventory[inventory["likely_type"]=="likely_descriptive"])}')
print(f'  - unknown: {len(inventory[inventory["likely_type"]=="unknown"])}')
print()
print(f'Unique tables extracted: {extracted["table_number"].nunique()}')
print(f'Rows extracted: {len(extracted)}')

# Get list of extracted table+study combinations
extracted_combos = set()
for _, row in extracted.iterrows():
    # Normalize study_id (remove hash prefix if present)
    study_id = str(row['study_id'])
    table = str(row['table_number'])
    extracted_combos.add((study_id, table))

# Check which likely_results were extracted
likely_results = inventory[inventory['likely_type'] == 'likely_results'].copy()

missed_results = []
for _, row in likely_results.iterrows():
    study_id = row['study_id']
    table_id = row['table_id']
    
    # Check if extracted (exact match or partial)
    found = False
    for ext_study, ext_table in extracted_combos:
        if study_id in ext_study or ext_study in study_id:
            if table_id == ext_table:
                found = True
                break
    
    if not found:
        missed_results.append(row)

print(f'\n\nPOTENTIAL FALSE NEGATIVES (likely_results NOT extracted): {len(missed_results)}')
print('-' * 80)
for row in missed_results[:40]:
    print(f"  {row['study_id'][:35]:35} | {row['table_id']:8} | {row['caption'][:45]}")

# Check likely_descriptive that were extracted (false positives)
likely_desc = inventory[inventory['likely_type'] == 'likely_descriptive'].copy()

wrongly_extracted = []
for _, row in likely_desc.iterrows():
    study_id = row['study_id']
    table_id = row['table_id']
    
    for ext_study, ext_table in extracted_combos:
        if study_id in ext_study or ext_study in study_id:
            if table_id == ext_table:
                wrongly_extracted.append(row)
                break

print(f'\n\nPOTENTIAL FALSE POSITIVES (likely_descriptive that WERE extracted): {len(wrongly_extracted)}')
print('-' * 80)
for row in wrongly_extracted[:30]:
    print(f"  {row['study_id'][:35]:35} | {row['table_id']:8} | {row['caption'][:45]}")

# Summary
print('\n\n' + '=' * 80)
print('SUMMARY')
print('=' * 80)
print(f'Tables with results keywords: {len(likely_results)}')
print(f'  - Extracted: {len(likely_results) - len(missed_results)}')
print(f'  - Missed (FN): {len(missed_results)}')
print()
print(f'Tables with descriptive keywords: {len(likely_desc)}')
print(f'  - Correctly skipped: {len(likely_desc) - len(wrongly_extracted)}')
print(f'  - Wrongly extracted (FP): {len(wrongly_extracted)}')
