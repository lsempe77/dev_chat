"""Check what tables precede the fragment tables."""
import pandas as pd

df = pd.read_csv('extraction_pipeline/outputs/classification_v3_test.csv')
fragment_indices = [26, 29, 31, 36, 38, 42, 52, 107]

print("Checking tables before fragments:\n")
for idx in fragment_indices:
    if idx > 0:
        prev = df.iloc[idx-1]
        curr = df.iloc[idx]
        print(f"Index {idx-1} -> {idx}")
        print(f"  PREV: page {prev['page']}, class={prev['classification']}, table={prev['table_number']}")
        print(f"  CURR: page {curr['page']}, class={curr['classification']}, table={curr['table_number']}")
        print(f"  Same page: {prev['page'] == curr['page']}")
        print()
