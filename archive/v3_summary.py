"""Summarize V3 extraction requirements."""
import pandas as pd

gt = pd.read_excel('8WR QEX Combined.xlsx')

print('=== V3 EXTRACTION REQUIREMENTS ===')
print()
print('1. METADATA (from master_UPG.csv):')
print('   - study_design: 97.7% baseline (target 98%+)')
print('   - country: 90.7% baseline (target 95%)')
print()
print('2. INTERVENTION COMPONENTS (7 binary):')
print('   - health_comp: 69.8% baseline (target 85%)')
print('   - skills_comp: 90.7% baseline (target 92%)')
print('   - savings_comp: 69.8% baseline (target 85%)')
print('   - coaching_comp: 72.1% baseline (target 85%)')
print('   - social_comp: 65.1% baseline (target 80%)')
print('   - targeting_women: 74.4% baseline (target 85%)')
print('   - consumption_support: NOT TESTED')
print('   - asset_transfer: NOT TESTED')
print()
print('3. OUTCOMES (per study, need to extract raw values):')

# What values are available
print(f'   Total outcomes in GT: {len(gt)}')
print(f'   Outcomes with Coeff reg: {gt["Coeff reg"].notna().sum()}')

se_col = [c for c in gt.columns if 'SE reg' in c][0]
print(f'   Outcomes with SE: {gt[se_col].notna().sum()}')
print(f'   Outcomes with N treatment: {gt["N treatment"].notna().sum()}')
print(f'   Outcomes with N control: {gt["N control "].notna().sum()}')

n_total_col = [c for c in gt.columns if 'N total' in c][0]
print(f'   Outcomes with N total: {gt[n_total_col].notna().sum()}')
print()
print('4. COHEN d FORMULA (verified exact):')
print('   d = (coef/se) * sqrt(1/n1 + 1/n2)')
print()
print('5. OUTCOME CATEGORIES:')
cats = gt['Outcome category'].value_counts()
for cat, count in cats.items():
    print(f'   {cat}: {count}')
