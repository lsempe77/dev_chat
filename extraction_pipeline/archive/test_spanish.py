"""Test improved classification on Spanish study."""
import pandas as pd
import sys
sys.path.insert(0, '.')
from extraction_pipeline.pipeline import classify_table_rules

# Load inventory
inv = pd.read_csv('extraction_pipeline/outputs/all_tables_inventory.csv')

# Find Spanish study
spanish = inv[inv['study_id'].str.contains('27cf2157fc9d')]

print("SPANISH STUDY (27cf2157fc9d) - Testing improved classification")
print("=" * 100)
print(f"Total tables: {len(spanish)}")
print()

results_count = 0
descriptive_count = 0
unknown_count = 0

print(f"{'Table':<10} | {'Old Type':<20} | {'New Classification':<15} | Caption")
print("-" * 100)

for _, row in spanish.iterrows():
    old_type = row['likely_type']
    new_class = classify_table_rules(row['caption'], '')
    
    if new_class == 'results':
        results_count += 1
        marker = "✅"
    elif new_class == 'descriptive':
        descriptive_count += 1
        marker = "❌"
    else:
        unknown_count += 1
        marker = "❓"
    
    print(f"{row['table_id']:<10} | {old_type:<20} | {marker} {new_class:<12} | {row['caption'][:45]}")

print()
print("=" * 100)
print(f"NEW CLASSIFICATION SUMMARY:")
print(f"  Results: {results_count}")
print(f"  Descriptive: {descriptive_count}")
print(f"  Unknown: {unknown_count}")
