"""
Create validation table from extraction stats for human ground truth review
"""
import pandas as pd

# Load the stats file
stats = pd.read_csv('extraction_pipeline/outputs/full_corpus_all_stats.csv')

# Create clean readable name
def get_readable_name(row):
    if pd.notna(row['study_name']) and row['study_name']:
        # BRAC study - format nicely
        parts = str(row['study_name']).split('_')
        if len(parts) >= 3:
            return f"{parts[0]} - {parts[1]} ({parts[2]})"
        return row['study_name']
    elif pd.notna(row['study_id']):
        return f"Study {int(row['study_id'])}"
    else:
        return str(row['identifier'])

# Create validation table
val_df = pd.DataFrame({
    'study_id': stats['identifier'],
    'readable_name': stats.apply(get_readable_name, axis=1),
    'rows_extracted': stats['rows'],
    'tables_processed': stats['tables'],
    'source': stats['source'],
    'pdf_filename': stats['filename'].str.replace('.json', '.pdf'),
    'validated': '',
    'accuracy_pct': '',
    'notes': ''
})

# Sort by rows descending
val_df = val_df.sort_values('rows_extracted', ascending=False)

# Save
val_df.to_csv('extraction_pipeline/outputs/validation_table.csv', index=False)
val_df.to_excel('extraction_pipeline/outputs/validation_table.xlsx', index=False)

# Summary
print('='*80)
print('VALIDATION TABLE CREATED')
print('='*80)
print(f"Total studies: {len(val_df)}")
print(f"With data (rows > 0): {len(val_df[val_df['rows_extracted'] > 0])}")  
print(f"Zero extraction: {len(val_df[val_df['rows_extracted'] == 0])}")
print(f"Total rows: {val_df['rows_extracted'].sum():,}")

print()
print('='*80)
print('TOP 15 STUDIES FOR VALIDATION (highest rows)')
print('='*80)
top = val_df.head(15)[['study_id', 'readable_name', 'rows_extracted', 'tables_processed', 'source']]
print(top.to_string(index=False))

print()
print('='*80)
print('ZERO EXTRACTION STUDIES')
print('='*80)
zero = val_df[val_df['rows_extracted'] == 0][['study_id', 'readable_name', 'pdf_filename']]
for _, row in zero.iterrows():
    name = row['readable_name'][:35]
    pdf = row['pdf_filename'][:60]
    print(f"{name:40} | {pdf}")

print()
print('Files saved:')
print('  - extraction_pipeline/outputs/validation_table.csv')
print('  - extraction_pipeline/outputs/validation_table.xlsx')
