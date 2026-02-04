"""Analyze table classification quality - TP, TN, FP, FN."""
import pandas as pd

# Load data
inventory = pd.read_csv('extraction_pipeline/outputs/all_tables_inventory.csv')
extracted = pd.read_csv('extraction_pipeline/outputs/full_corpus_for_validation.csv')

print("=" * 100)
print("TABLE CLASSIFICATION ANALYSIS")
print("=" * 100)

# Get unique extracted tables
extracted_tables = extracted.groupby(['study_id', 'table_number']).agg({
    'table_caption': 'first',
    'outcome_name': 'count'
}).reset_index()
extracted_tables.columns = ['study_id', 'table_id', 'caption', 'rows']

print(f"\n📊 EXTRACTED TABLES: {len(extracted_tables)} unique tables, {len(extracted)} rows")
print("-" * 100)
print(f"{'Study ID':<40} | {'Table':<10} | {'Rows':>5} | Caption")
print("-" * 100)

# Categorize extracted tables
fp_keywords = ['baseline', 'balance', 'attrition', 'sample size', 'descriptive', 'summary stat']
maybe_fp = []
likely_tp = []

for _, row in extracted_tables.iterrows():
    caption_lower = str(row['caption']).lower()
    is_fp = any(kw in caption_lower for kw in fp_keywords)
    
    if is_fp:
        maybe_fp.append(row)
        marker = "⚠️ FP?"
    else:
        likely_tp.append(row)
        marker = "✅"
    
    # Only print first 50
    if len(maybe_fp) + len(likely_tp) <= 60:
        print(f"{str(row['study_id'])[:40]:<40} | {row['table_id']:<10} | {row['rows']:>5} | {marker} {str(row['caption'])[:50]}")

print(f"\n... showing first 60 of {len(extracted_tables)} tables")

# Summary
print("\n" + "=" * 100)
print("CLASSIFICATION SUMMARY")
print("=" * 100)

# Inventory analysis
likely_results = inventory[inventory['likely_type'] == 'likely_results']
likely_desc = inventory[inventory['likely_type'] == 'likely_descriptive']
unknown = inventory[inventory['likely_type'] == 'unknown']

print(f"""
📋 INVENTORY (all tables in documents):
   - Total tables found: {len(inventory)}
   - likely_results (has effect/impact/coefficient keywords): {len(likely_results)}
   - likely_descriptive (has baseline/balance/attrition): {len(likely_desc)}
   - unknown (no clear keywords): {len(unknown)}

📤 EXTRACTED:
   - Tables extracted: {len(extracted_tables)}
   - Rows extracted: {len(extracted)}
   - Likely True Positives: {len(likely_tp)} (good extractions)
   - Potential False Positives: {len(maybe_fp)} (may be descriptive)

📊 CLASSIFICATION QUALITY:
""")

# Calculate metrics
print(f"   FALSE POSITIVES (Descriptive tables we extracted): {len(maybe_fp)}")
for row in maybe_fp:
    print(f"      ⚠️  {row['table_id']}: {str(row['caption'])[:60]}")

print(f"\n   FALSE NEGATIVES (Results tables we MISSED): estimated {len(likely_results) - len(likely_tp)}")
print(f"      (Tables with 'effect', 'impact', 'coefficient' that weren't extracted)")

# Export for review
print("\n\n" + "=" * 100)
print("EXPORTING FOR MANUAL REVIEW")
print("=" * 100)

# Save extracted table names
extracted_tables.to_csv('extraction_pipeline/outputs/extracted_table_names.csv', index=False)
print(f"✅ Saved: extracted_table_names.csv ({len(extracted_tables)} tables)")

# Save potential false positives
fp_df = pd.DataFrame(maybe_fp)
fp_df.to_csv('extraction_pipeline/outputs/potential_false_positives.csv', index=False)
print(f"✅ Saved: potential_false_positives.csv ({len(maybe_fp)} tables)")

# Save potential false negatives (likely_results not in extracted)
extracted_set = set(extracted_tables['table_id'].values)
missed = likely_results[~likely_results['table_id'].isin(extracted_set)]
missed.to_csv('extraction_pipeline/outputs/potential_false_negatives.csv', index=False)
print(f"✅ Saved: potential_false_negatives.csv ({len(missed)} tables)")
