"""
Analyze significance extraction in the pipeline output.
"""

import pandas as pd

df = pd.read_csv("extraction_pipeline/outputs/121058356/extracted_data.csv")

print("SIGNIFICANCE ANALYSIS")
print("=" * 60)

# Check significance distribution
print("\n1. Significance values distribution:")
print(df["significance"].value_counts(dropna=False))

# Check rows WITHOUT significance
no_sig = df[df["significance"].isna()]
print(f"\n2. Rows without significance: {len(no_sig)}/{len(df)} ({len(no_sig)/len(df)*100:.1f}%)")

# Sample some literal_cell_text where significance is missing
print("\n3. Sample cells WITHOUT significance extracted:")
for i, (_, row) in enumerate(no_sig.head(10).iterrows()):
    cell = row["literal_cell_text"]
    print(f'   "{cell}"')

# Check if any cells have stars that weren't extracted
print("\n4. Checking for MISSED stars in cells without significance:")
missed_count = 0
for _, row in no_sig.iterrows():
    cell = str(row["literal_cell_text"])
    if "*" in cell:
        if missed_count < 5:
            print(f'   MISSED: "{cell}"')
        missed_count += 1

print(f"\n   Total cells with * but no significance extracted: {missed_count}")

# Check cells WITH significance
print("\n5. Sample cells WITH significance extracted:")
with_sig = df[df["significance"].notna()]
for i, (_, row) in enumerate(with_sig.head(5).iterrows()):
    print(f'   "{row["literal_cell_text"]}" -> sig="{row["significance"]}"')

# Check if significance maps to p-values
print("\n6. Significance star mapping (Issue #2):")
print("   Current: Just extracts *, **, ***")
print("   Missing: No mapping to p<.001, p<.01, p<.05")
print("   Missing: No footnote extraction for significance definitions")
