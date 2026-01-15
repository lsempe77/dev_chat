"""Check what LLM extracted for Bossuroy study."""

import json

with open('v17d_cohens_d_results.json') as f:
    data = json.load(f)

for study in data['studies']:
    if study['study_id'] == '121058356':
        print(f"Study: {study['author']}")
        print(f"Total outcomes extracted: {len(study['enriched_outcomes'])}")
        print()
        
        # Group by table_source
        by_table = {}
        for o in study['enriched_outcomes']:
            table = o.get('table_source', 'unknown')
            if table not in by_table:
                by_table[table] = []
            by_table[table].append(o)
        
        print("By table:")
        for table, outcomes in sorted(by_table.items()):
            print(f"  {table}: {len(outcomes)} outcomes")
        
        print()
        print("All outcomes:")
        for i, o in enumerate(study['enriched_outcomes']):
            name = o.get('outcome_name', '')[:60]
            table = o.get('table_source', '')
            coef = o.get('coefficient')
            se = o.get('standard_error')
            print(f"{i+1:3}. [{table}] {name}")
            print(f"     coef={coef}, se={se}")
