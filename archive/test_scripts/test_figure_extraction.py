"""Test figure extraction on zero-extraction studies."""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

os.environ['AWS_ACCESS_KEY_ID'] = os.environ.get('R2_ACCESS_KEY_ID', '')
os.environ['AWS_SECRET_ACCESS_KEY'] = os.environ.get('R2_SECRET_ACCESS_KEY', '')

import pandas as pd
from extraction_pipeline.pipeline import (
    load_mineru_json, 
    extract_all_tables, 
    extract_effects_from_prose,
    extract_effects_from_figures
)

# Zero-extraction studies from V5
zero_studies = ['121058361', '121766336']

print(f'Testing figure extraction on {len(zero_studies)} zero-extraction studies...')
print('=' * 70)

results = []

for sid in zero_studies:
    print(f'\n--- Study {sid} ---')
    
    doc = load_mineru_json(sid)
    if doc is None:
        print(f'  ERROR: Could not load document')
        results.append({'study_id': sid, 'source': 'none', 'rows': 0})
        continue
    
    n_tables = len(doc.get('tables', []))
    n_chars = len(doc.get('content', ''))
    print(f'  Loaded: {n_tables} tables, {n_chars} chars')
    
    # Try table extraction first
    df_tables = extract_all_tables(doc, sid, use_llm=False)
    print(f'  Table extraction: {len(df_tables)} rows')
    
    # Try prose extraction
    prose_effects = extract_effects_from_prose(doc, sid)
    print(f'  Prose extraction: {len(prose_effects)} rows')
    
    # Try figure extraction
    figure_effects = extract_effects_from_figures(doc, sid)
    print(f'  Figure extraction: {len(figure_effects)} rows')
    
    # Determine best source
    if len(df_tables) > 0:
        results.append({'study_id': sid, 'source': 'tables', 'rows': len(df_tables)})
    elif len(prose_effects) > 0:
        results.append({'study_id': sid, 'source': 'prose', 'rows': len(prose_effects)})
    elif len(figure_effects) > 0:
        results.append({'study_id': sid, 'source': 'figures', 'rows': len(figure_effects)})
        # Show figure effects
        print(f'\n  Figure effects extracted:')
        for i, e in enumerate(figure_effects):
            print(f'    {i+1}. {e.get("outcome_name", "N/A")} ({e.get("treatment_arm", "N/A")})')
            print(f'       Coef: {e.get("coefficient", "N/A")}, Dir: {e.get("effect_direction", "N/A")}, Sig: {e.get("significance", "N/A")}')
    else:
        results.append({'study_id': sid, 'source': 'none', 'rows': 0})

# Summary
print('\n' + '=' * 70)
print('FIGURE EXTRACTION SUMMARY')
print('=' * 70)
df_results = pd.DataFrame(results)
print(df_results.to_string(index=False))

extracted = len(df_results[df_results['rows'] > 0])
print(f'\nStudies with data: {extracted}/{len(zero_studies)}')
print(f'Total rows: {df_results["rows"].sum()}')
