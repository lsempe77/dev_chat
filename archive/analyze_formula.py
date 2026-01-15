"""Reverse-engineer the Cohen's d formula from ground truth data."""
import pandas as pd
import numpy as np

gt = pd.read_excel('8WR QEX Combined.xlsx')

# Print actual column names to see the exact format
print('=== COLUMN NAMES (relevant) ===')
for col in gt.columns:
    if 'reg' in col.lower() or 'n ' in col.lower() or col == 'd':
        print(f'  "{col}" (repr: {repr(col)})')
print()

# Find SE column with regex
se_col = [c for c in gt.columns if 'SE reg' in c][0]
tstat_col = [c for c in gt.columns if 'Tstat' in c][0]
n_total_col = [c for c in gt.columns if 'N total' in c][0]

# Analyze what data is available for each formula
print('=== FORMULA 5 ANALYSIS (142 rows) ===')
f5 = gt[gt['Formula Used'] == 5.0]
print(f'Has Coeff reg: {f5["Coeff reg"].notna().sum()}')
print(f'Has SE reg: {f5[se_col].notna().sum()}')
print(f'Has N treatment: {f5["N treatment"].notna().sum()}')
print(f'Has N control: {f5["N control "].notna().sum()}')
print(f'Has Tstat reg: {f5[tstat_col].notna().sum()}')
print()

print('=== FORMULA 6 ANALYSIS (300 rows) ===')
f6 = gt[gt['Formula Used'] == 6.0]
print(f'Has Coeff reg: {f6["Coeff reg"].notna().sum()}')
print(f'Has SE reg: {f6[se_col].notna().sum()}')
print(f'Has N treatment: {f6["N treatment"].notna().sum()}')
print(f'Has N control: {f6["N control "].notna().sum()}')
print(f'Has Tstat reg: {f6[tstat_col].notna().sum()}')
print(f'Has N total: {f6[n_total_col].notna().sum()}')
print()

# Try to reverse-engineer the formula
print('=== REVERSE ENGINEERING FORMULA 5 ===')
# For formula 5: has N treatment, N control
sample_f5 = f5[['Coeff reg', se_col, 'N treatment', 'N control ', 'd']].dropna().head(5)
for idx, row in sample_f5.iterrows():
    coef = row['Coeff reg']
    se = row[se_col]
    n1 = row['N treatment']
    n2 = row['N control ']
    d_actual = row['d']
    
    # Try different formulas
    t = coef / se
    d_from_t = t * np.sqrt(1/n1 + 1/n2)
    
    print(f'Row {idx}: coef={coef:.3f}, se={se:.4f}, t={t:.3f}, n1={n1:.0f}, n2={n2:.0f}')
    print(f'  d_actual={d_actual:.4f}, d_from_t={d_from_t:.4f}, error={abs(d_actual-d_from_t):.6f}')

print()
print('=== REVERSE ENGINEERING FORMULA 6 ===')
# For formula 6: no sample sizes, likely t-stat based
sample_f6 = f6[['Coeff reg', se_col, 'd']].dropna().head(5)
for idx, row in sample_f6.iterrows():
    coef = row['Coeff reg']
    se = row[se_col]
    d_actual = row['d']
    
    # Check if d = coef/se (standardized coef)
    d_guess1 = coef / se
    
    # Or maybe just coef already is d?
    print(f'Row {idx}: coef={coef:.4f}, se={se:.4f}, d={d_actual:.6f}')
    print(f'  coef/se={coef/se:.6f}')
    print(f'  Ratio d/coef = {d_actual/coef:.6f}' if coef != 0 else '  coef=0')

print()
print('=== CHECK IF d = coef / (se * constant) ===')
# For formula 6, find the scaling factor
f6_valid = f6[['Coeff reg', se_col, 'd']].dropna().copy()
f6_valid['ratio'] = f6_valid['d'] / f6_valid['Coeff reg']
f6_valid['ratio_se'] = f6_valid['d'] * f6_valid[se_col] / f6_valid['Coeff reg']
print(f'Mean ratio (d/coef): {f6_valid["ratio"].mean():.6f}')
print(f'Std ratio: {f6_valid["ratio"].std():.6f}')
print(f'Sample ratios: {f6_valid["ratio"].head(10).tolist()}')
