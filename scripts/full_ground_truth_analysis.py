"""Complete analysis of ALL columns in ground truth files."""
import pandas as pd

# Load files
qex = pd.read_excel('data/8WR QEX Combined.xlsx', sheet_name='Sheet1')
om = pd.read_excel('data/8 week SR OM Combined.xlsx', sheet_name='OM for 50 studies')

print("=" * 80)
print("COMPLETE GROUND TRUTH ANALYSIS")
print("=" * 80)

print(f"\n{'='*80}")
print("QEX FILE - ALL {len(qex.columns)} COLUMNS WITH COVERAGE")
print(f"{'='*80}")
print(f"Total rows: {len(qex)}")

for i, col in enumerate(qex.columns):
    filled = qex[col].notna().sum()
    pct = filled / len(qex) * 100
    # Get sample value
    sample = qex[col].dropna().iloc[0] if filled > 0 else "N/A"
    if isinstance(sample, str) and len(sample) > 50:
        sample = sample[:50] + "..."
    print(f"{i:3d}. {col[:50]:50s} | {filled:4d} ({pct:5.1f}%) | Sample: {sample}")

print(f"\n{'='*80}")
print(f"OM FILE - ALL {len(om.columns)} COLUMNS WITH COVERAGE")
print(f"{'='*80}")
print(f"Total rows: {len(om)}")

for i, col in enumerate(om.columns):
    filled = om[col].notna().sum()
    pct = filled / len(om) * 100
    sample = om[col].dropna().iloc[0] if filled > 0 else "N/A"
    if isinstance(sample, str) and len(sample) > 50:
        sample = sample[:50] + "..."
    print(f"{i:3d}. {col[:50]:50s} | {filled:4d} ({pct:5.1f}%) | Sample: {sample}")

# Check which columns are in both files
print(f"\n{'='*80}")
print("COLUMN OVERLAP ANALYSIS")
print(f"{'='*80}")
qex_cols = set(qex.columns)
om_cols = set(om.columns)
shared = qex_cols & om_cols
print(f"Columns in both: {len(shared)}")
for col in sorted(shared):
    print(f"  - {col}")

print(f"\nColumns only in OM ({len(om_cols - qex_cols)}):")
for col in sorted(om_cols - qex_cols):
    print(f"  - {col}")
