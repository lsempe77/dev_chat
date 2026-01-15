"""Check accuracy for exact outcome matches only."""

import pandas as pd

df = pd.read_csv('cohens_d_mapped_comparison.csv')

# Only exact matches
exact = df[df['match_score'] == 1.0]
print(f'Exact name matches: {len(exact)}')

close = exact[exact['difference'] < 0.1]
print(f'Exact matches with close d: {len(close)} ({100*len(close)/len(exact):.1f}%)')

print('\nExact matches:')
for _, row in exact.iterrows():
    status = 'CLOSE' if row['difference'] < 0.1 else 'MISMATCH'
    extracted = row['extracted_outcome'][:50]
    ext_d = row['extracted_d']
    gt_d = row['gt_d']
    diff = row['difference']
    print(f'  [{status}] {extracted}')
    print(f'    Extracted: {ext_d:.4f}, GT: {gt_d:.4f}, Diff: {diff:.4f}')
