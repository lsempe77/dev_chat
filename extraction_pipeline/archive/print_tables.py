"""Print all extracted table names with row counts."""
import pandas as pd

df = pd.read_csv('extraction_pipeline/outputs/full_corpus_for_validation.csv')

# Get unique table captions with row counts
table_info = df.groupby(['table_number', 'table_caption']).size().reset_index(name='rows')
table_info = table_info.sort_values('rows', ascending=False)

print('TOP 100 TABLES BY ROW COUNT:')
print('=' * 110)
print(f"{'ROWS':>5} | {'TABLE':12} | CAPTION")
print('-' * 110)

for _, row in table_info.head(100).iterrows():
    caption = str(row['table_caption'])[:80] if pd.notna(row['table_caption']) else 'N/A'
    print(f"{row['rows']:5d} | {row['table_number']:12} | {caption}")

print('\n' + '=' * 110)
print(f"Total unique tables: {len(table_info)}")
print(f"Total rows: {len(df)}")

# Show suspicious table names (likely NOT treatment effects)
print('\n\nPOTENTIALLY WRONG TABLES (descriptive keywords in caption):')
print('-' * 110)
suspicious_keywords = ['balance', 'baseline', 'summary', 'sample', 'number of', 'attrition', 
                       'compliance', 'definition', 'description', 'characteristic']

for _, row in table_info.iterrows():
    caption_lower = str(row['table_caption']).lower()
    for kw in suspicious_keywords:
        if kw in caption_lower:
            print(f"{row['rows']:5d} | {row['table_number']:12} | {str(row['table_caption'])[:80]}")
            break
