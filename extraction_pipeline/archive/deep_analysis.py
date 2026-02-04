"""Deep analysis of False Positives and False Negatives to plan improvements."""
import pandas as pd
from collections import Counter

print("=" * 100)
print("DEEP ANALYSIS OF FALSE POSITIVES AND FALSE NEGATIVES")
print("=" * 100)

# Load all data
inv = pd.read_csv('extraction_pipeline/outputs/all_tables_inventory.csv')
ext = pd.read_csv('extraction_pipeline/outputs/full_corpus_for_validation.csv')

print(f"\n📊 DATA SOURCES:")
print(f"   Inventory: {len(inv)} tables from {inv['study_id'].nunique()} studies")
print(f"   Extracted: {len(ext)} rows from {ext['study_id'].nunique()} studies, {ext['table_number'].nunique()} unique tables")

# Get extracted table names with captions
ext_tables = ext.groupby(['study_id', 'table_number']).agg({
    'table_caption': 'first'
}).reset_index()

# ============================================================================
# FALSE POSITIVES ANALYSIS
# ============================================================================
print("\n\n" + "=" * 100)
print("FALSE POSITIVES (Descriptive tables we INCORRECTLY extracted)")
print("=" * 100)

# Keywords that indicate descriptive (non-results) tables
fp_keywords = [
    'baseline', 'balance', 'attrition', 'sample size', 'descriptive', 
    'summary stat', 'characteristics', 'compliance', 'randomization'
]

fp_tables = []
for _, row in ext_tables.iterrows():
    caption = str(row['table_caption']).lower()
    for kw in fp_keywords:
        if kw in caption:
            fp_tables.append({
                'study_id': row['study_id'],
                'table': row['table_number'],
                'caption': row['table_caption'],
                'keyword_match': kw
            })
            break

print(f"\nFound {len(fp_tables)} potential False Positives:\n")
fp_by_keyword = Counter([t['keyword_match'] for t in fp_tables])
print("By keyword:")
for kw, count in fp_by_keyword.most_common():
    print(f"   {kw}: {count}")

print("\n\nDetailed list:")
print("-" * 100)
for t in fp_tables:
    print(f"   {t['keyword_match']:15} | {t['table']:10} | {t['caption'][:60]}")

# ============================================================================
# FALSE NEGATIVES ANALYSIS  
# ============================================================================
print("\n\n" + "=" * 100)
print("FALSE NEGATIVES (Results tables we MISSED)")
print("=" * 100)

# Tables from inventory that have results keywords but weren't extracted
likely_results = inv[inv['likely_type'] == 'likely_results'].copy()

# Build set of extracted (study_hash, table_id) for matching
extracted_set = set()
for _, row in ext_tables.iterrows():
    study = str(row['study_id'])
    table = str(row['table_number'])
    extracted_set.add((study, table))
    
# Also add with hash prefix matching
for _, row in ext_tables.iterrows():
    extracted_set.add(row['table_number'])  # Just table ID

# Find missed tables
missed = []
for _, row in likely_results.iterrows():
    # Check if this table was extracted (by table_id alone since study_ids differ)
    table_id = row['table_id']
    study_id = row['study_id']
    
    # Try to match by study hash prefix + table
    found = False
    for ext_study, ext_table in [(r['study_id'], r['table_number']) for _, r in ext_tables.iterrows()]:
        # Hash prefix match (first 12 chars)
        if study_id[:12] in str(ext_study) or str(ext_study) in study_id:
            if table_id == ext_table:
                found = True
                break
    
    if not found:
        missed.append(row)

print(f"\nFound {len(missed)} potential False Negatives (likely results we missed):\n")

# Analyze patterns in missed tables
missed_df = pd.DataFrame(missed)
print(f"From {missed_df['study_id'].nunique()} different studies")

# Count by caption keywords
fn_keywords = Counter()
for cap in missed_df['caption'].values:
    cap_lower = str(cap).lower()
    if 'treatment effect' in cap_lower:
        fn_keywords['treatment effect'] += 1
    elif 'impact' in cap_lower:
        fn_keywords['impact'] += 1
    elif 'effect' in cap_lower:
        fn_keywords['effect'] += 1
    elif 'regression' in cap_lower:
        fn_keywords['regression'] += 1
    elif 'coefficient' in cap_lower:
        fn_keywords['coefficient'] += 1
    else:
        fn_keywords['other'] += 1

print("\nMissed tables by keyword type:")
for kw, count in fn_keywords.most_common():
    print(f"   {kw}: {count}")

print("\n\nSample of missed tables (first 40):")
print("-" * 100)
for i, row in missed_df.head(40).iterrows():
    print(f"   {row['study_id'][:30]:30} | {row['table_id']:10} | {row['caption'][:50]}")

# ============================================================================
# ROOT CAUSE ANALYSIS
# ============================================================================
print("\n\n" + "=" * 100)
print("ROOT CAUSE ANALYSIS")
print("=" * 100)

# Check which studies have the most missed tables
missed_by_study = missed_df.groupby('study_id').size().sort_values(ascending=False)
print(f"\nStudies with most missed tables:")
for study, count in missed_by_study.head(10).items():
    print(f"   {study[:50]}: {count} tables missed")

# Check if some studies have NO extractions at all
inv_studies = set(inv['study_id'].unique())
ext_study_hashes = set()
for s in ext['study_id'].unique():
    ext_study_hashes.add(str(s)[:12])

print(f"\n\nStudies in inventory: {len(inv_studies)}")
print(f"Studies with extractions: {ext['study_id'].nunique()}")

# ============================================================================
# IMPROVEMENT RECOMMENDATIONS
# ============================================================================
print("\n\n" + "=" * 100)
print("IMPROVEMENT RECOMMENDATIONS")
print("=" * 100)

print("""
1. FALSE POSITIVE FIXES:
   - Add "baseline characteristics" to SKIP list
   - Add "balance" tables to SKIP list  
   - Add "attrition" to SKIP list
   - BUT: "Heterogeneity by baseline" may actually contain treatment effects!
   
2. FALSE NEGATIVE FIXES:
   - Some studies may have failed extraction entirely
   - LLM classification may be too conservative
   - Tables without clear "effect" in caption may have results
   
3. NEXT STEPS:
   a) Re-run extraction with updated classification rules
   b) Check if LLM two-pass classification helps
   c) Manual review of top missed studies
""")

# Save detailed analysis
missed_df.to_csv('extraction_pipeline/outputs/fn_detailed.csv', index=False)
pd.DataFrame(fp_tables).to_csv('extraction_pipeline/outputs/fp_detailed.csv', index=False)
print("\n✅ Saved: fn_detailed.csv, fp_detailed.csv")
