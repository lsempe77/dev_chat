"""Check if there are duplicate table numbers."""
import pandas as pd
df = pd.read_csv('extraction_pipeline/outputs/classification_v3_test.csv')

# Find tables with similar names to our SKIPs
skip_table_numbers = ['7.3a', '7.4a', '7.5a', '7.5b', '7.6b', '7.8b']

for num in skip_table_numbers:
    matches = df[df['table_number'].str.contains(num, na=False)]
    print(f'Tables containing {num}:')
    for _, r in matches.iterrows():
        print(f"  idx={r['index']}, pg={r['page']}, class={r['classification']}, rows={r['rows']}")
    print()

# Summary of SKIPs by reason
print("\n=== SKIP REASONS BREAKDOWN ===")
skips = df[df['classification'] == 'SKIP']
print(skips['reason'].value_counts())
