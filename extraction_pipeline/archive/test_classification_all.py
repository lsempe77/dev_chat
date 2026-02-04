"""
Test table classification on ALL inventory tables.
Compare old heuristic vs new rules to measure improvement.
"""
import pandas as pd
import sys
sys.path.insert(0, '.')
from extraction_pipeline.pipeline import classify_table_rules

# Load inventory
inv = pd.read_csv('extraction_pipeline/outputs/all_tables_inventory.csv')

print("=" * 100)
print("TABLE CLASSIFICATION TEST - ALL 1,835 TABLES")
print("=" * 100)

# Classify all tables with new rules
results = []
for _, row in inv.iterrows():
    new_class = classify_table_rules(row['caption'], '')
    results.append({
        'study_id': row['study_id'],
        'table_id': row['table_id'],
        'caption': row['caption'],
        'old_type': row['likely_type'],
        'new_class': new_class,
    })

df = pd.DataFrame(results)

# Summary by new classification
print("\n📊 NEW CLASSIFICATION DISTRIBUTION:")
print("-" * 50)
for cls, count in df['new_class'].value_counts().items():
    pct = count / len(df) * 100
    print(f"  {cls:15}: {count:5} ({pct:.1f}%)")

# Compare old vs new
print("\n\n📊 OLD vs NEW COMPARISON:")
print("-" * 50)
cross = pd.crosstab(df['old_type'], df['new_class'], margins=True)
print(cross)

# Key improvements
print("\n\n✅ KEY IMPROVEMENTS:")
print("-" * 50)

# Tables that were "unknown" but now classified as results
unknown_to_results = df[(df['old_type'] == 'unknown') & (df['new_class'] == 'results')]
print(f"Unknown → Results: {len(unknown_to_results)} tables")
if len(unknown_to_results) > 0:
    print("  Examples:")
    for _, r in unknown_to_results.head(10).iterrows():
        print(f"    {r['table_id']:10} | {r['caption'][:55]}")

# Tables that had "likely_results" and now confirmed
likely_confirmed = df[(df['old_type'] == 'likely_results') & (df['new_class'] == 'results')]
print(f"\nlikely_results → results (confirmed): {len(likely_confirmed)} tables")

# Problem: likely_results but now unknown (need LLM)
likely_unknown = df[(df['old_type'] == 'likely_results') & (df['new_class'] == 'unknown')]
print(f"\nlikely_results → unknown (need LLM): {len(likely_unknown)} tables")
if len(likely_unknown) > 0:
    print("  Examples:")
    for _, r in likely_unknown.head(10).iterrows():
        print(f"    {r['table_id']:10} | {r['caption'][:55]}")

# Problem: likely_results but now descriptive (potential issue!)
likely_desc = df[(df['old_type'] == 'likely_results') & (df['new_class'] == 'descriptive')]
print(f"\n⚠️ likely_results → descriptive (CHECK!): {len(likely_desc)} tables")
if len(likely_desc) > 0:
    print("  These might be ERRORS:")
    for _, r in likely_desc.iterrows():
        print(f"    {r['table_id']:10} | {r['caption'][:55]}")

# Tables that should be skipped
print("\n\n❌ TABLES TO SKIP (descriptive):")
print("-" * 50)
descriptive = df[df['new_class'] == 'descriptive']
print(f"Total: {len(descriptive)} tables")
print("Examples:")
for _, r in descriptive.head(15).iterrows():
    print(f"  {r['table_id']:10} | {r['caption'][:60]}")

# Unknown tables (need LLM)
print("\n\n❓ UNKNOWN TABLES (need LLM classification):")
print("-" * 50)
unknown = df[df['new_class'] == 'unknown']
print(f"Total: {len(unknown)} tables")
print("Sample:")
for _, r in unknown.sample(min(20, len(unknown))).iterrows():
    print(f"  {r['table_id']:10} | {r['caption'][:60]}")

# Results tables
print("\n\n✅ RESULTS TABLES (will be extracted):")
print("-" * 50)
results_tables = df[df['new_class'] == 'results']
print(f"Total: {len(results_tables)} tables")

# Group by study
by_study = results_tables.groupby('study_id').size().sort_values(ascending=False)
print(f"\nStudies with most results tables:")
for study, count in by_study.head(10).items():
    print(f"  {study[:50]:50} : {count} tables")

# Save results
df.to_csv('extraction_pipeline/outputs/classification_test.csv', index=False)
print("\n\n✅ Saved: classification_test.csv")

# Final summary
print("\n\n" + "=" * 100)
print("FINAL SUMMARY")
print("=" * 100)
print(f"""
Total tables in inventory: {len(inv)}

NEW CLASSIFICATION:
  ✅ Results (extract):      {len(results_tables):5} ({len(results_tables)/len(inv)*100:.1f}%)
  ❌ Descriptive (skip):     {len(descriptive):5} ({len(descriptive)/len(inv)*100:.1f}%)
  ❓ Unknown (need LLM):     {len(unknown):5} ({len(unknown)/len(inv)*100:.1f}%)

COMPARISON TO OLD:
  - Old "likely_results":    {len(inv[inv['likely_type']=='likely_results'])} tables
  - New "results":           {len(results_tables)} tables
  - Improvement:             +{len(results_tables) - len(inv[inv['likely_type']=='likely_results'])} tables

NEXT STEPS:
  1. Review the {len(likely_desc)} tables marked as likely_results → descriptive (check for errors)
  2. The {len(unknown)} "unknown" tables need LLM classification
  3. Run full extraction with these rules + LLM for unknowns
""")
