"""Analyze ground truth Excel files for field extraction planning."""
import pandas as pd

# Load files
qex = pd.read_excel('data/8WR QEX Combined.xlsx', sheet_name='Sheet1')
om = pd.read_excel('data/8 week SR OM Combined.xlsx', sheet_name='OM for 50 studies')

print("=" * 60)
print("GROUND TRUTH ANALYSIS FOR FIELD EXTRACTION")
print("=" * 60)

print("\n=== QEX FILE (Quantitative Extraction) ===")
print(f"Total estimates: {len(qex)}")
print(f"Unique studies: {qex['StudyID'].nunique()}")

print("\n--- Core Effect Size Fields ---")
core_fields = {
    'Coeff reg': 'Regression coefficient',
    'SE reg ': 'Standard error',
    'Tstat reg ': 'T-statistic',
    'CI_LB reg ': 'CI lower bound',
    'CI_UP reg ': 'CI upper bound',
    'P value exact ': 'Exact p-value',
    'N treatment': 'N treatment',
    'N control': 'N control',
    'N total ': 'N total',
    'd': "Cohen's d",
}
for col, desc in core_fields.items():
    if col in qex.columns:
        filled = qex[col].notna().sum()
        pct = filled / len(qex) * 100
        print(f"  {desc:25s}: {filled:4d} ({pct:5.1f}%)")

print("\n--- Metadata Fields ---")
meta_fields = {
    'Author name': 'Author',
    'Year of publication': 'Year',
    'Country': 'Country',
    'Intervention abbreviation and name': 'Intervention',
    'Outcome category': 'Outcome category',
    'Outcome name': 'Outcome name',
    'Outcome description': 'Outcome description',
    'Length of follow up': 'Follow-up length',
    'Treatment': 'Treatment arm',
}
for col, desc in meta_fields.items():
    if col in qex.columns:
        filled = qex[col].notna().sum()
        pct = filled / len(qex) * 100
        print(f"  {desc:25s}: {filled:4d} ({pct:5.1f}%)")

print("\n--- Intervention Components ---")
comp_fields = ['health_comp', 'skills_comp', 'savings_comp', 'coaching_comp', 'social_comp']
for col in comp_fields:
    if col in qex.columns:
        filled = qex[col].notna().sum()
        pct = filled / len(qex) * 100
        print(f"  {col:25s}: {filled:4d} ({pct:5.1f}%)")

print("\n=== OUTCOME CATEGORIES ===")
print(qex['Outcome category'].value_counts())

print("\n\n=== OM FILE (Outcome Mapping) ===")
print(f"Total rows: {len(om)}")
print(f"Columns: {len(om.columns)}")

print("\n--- OM Unique Fields (not in QEX) ---")
om_unique = [
    'Location of data to be extracted\n(page #; table #; table label; row label; column label)',
    'Table type',
    'Is the coef mentioned in the text? If yes, add start/whole sentence and page #.',
    'Reports on any tertiary outcomes? (Yes/No)',
    'Reports spillover analyses? (Yes/No)',
    'Reports subgroup analyses (yes/no)',
]
for col in om_unique:
    if col in om.columns:
        filled = om[col].notna().sum()
        pct = filled / len(om) * 100
        print(f"  {col[:40]:40s}: {filled:4d} ({pct:5.1f}%)")

print("\n=== TABLE TYPES ===")
if 'Table type' in om.columns:
    print(om['Table type'].value_counts())
