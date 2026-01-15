"""Compare V12 vs V13 results."""
import json

# Load both results
with open('extraction_pipeline/v12_results.json') as f:
    v12 = json.load(f)

with open('extraction_pipeline/v13_results.json') as f:
    v13 = json.load(f)

print('=' * 100)
print('V12 vs V13 DETAILED COMPARISON')
print('=' * 100)

# Create lookup by study_id
v12_by_id = {s['study_id']: s for s in v12['results']}
v13_by_id = {s['study_id']: s for s in v13['studies']}

header = f"{'Study':<30} {'V12 Ext':>8} {'V13 Ext':>8} {'Diff':>8} {'V12 Mat':>8} {'V13 Mat':>8} {'V12 R%':>8} {'V13 R%':>8}"
print(header)
print('-' * 100)

total_v12_ext, total_v13_ext = 0, 0
total_v12_mat, total_v13_mat = 0, 0

for study_id, v13_s in sorted(v13_by_id.items(), key=lambda x: x[1].get('author', '')):
    v12_s = v12_by_id.get(study_id, {})
    
    v12_ext = v12_s.get('num_outcomes_extracted', 0)
    v13_ext = v13_s.get('n_extracted', 0)
    v12_mat = v12_s.get('num_matched', 0)
    v13_mat = v13_s.get('n_matched', 0)
    v12_r = v12_s.get('recall', 0) * 100
    v13_r = v13_s.get('recall', 0) * 100
    
    total_v12_ext += v12_ext
    total_v13_ext += v13_ext
    total_v12_mat += v12_mat
    total_v13_mat += v13_mat
    
    diff = v13_ext - v12_ext
    author = v13_s.get('author', study_id)[:28]
    
    # Highlight big differences
    flag = ' ***' if abs(diff) > 50 else ''
    
    row = f"{author:<30} {v12_ext:>8} {v13_ext:>8} {diff:>+8} {v12_mat:>8} {v13_mat:>8} {v12_r:>7.1f}% {v13_r:>7.1f}%{flag}"
    print(row)

print('-' * 100)
totals = f"{'TOTAL':<30} {total_v12_ext:>8} {total_v13_ext:>8} {total_v13_ext-total_v12_ext:>+8} {total_v12_mat:>8} {total_v13_mat:>8}"
print(totals)

print()
print('=' * 100)
print('SUMMARY')
print('=' * 100)
print(f'  V12: {total_v12_ext} extracted, {total_v12_mat} matched ({total_v12_mat/442*100:.1f}% recall, {total_v12_mat/total_v12_ext*100:.1f}% precision)')
print(f'  V13: {total_v13_ext} extracted, {total_v13_mat} matched ({total_v13_mat/442*100:.1f}% recall, {total_v13_mat/total_v13_ext*100:.1f}% precision)')
print(f'  Difference: +{total_v13_ext-total_v12_ext} extractions, +{total_v13_mat-total_v12_mat} matches')
print()

# Calculate how many studies improved/worsened
improved = sum(1 for sid in v13_by_id if v13_by_id[sid].get('n_matched', 0) > v12_by_id.get(sid, {}).get('num_matched', 0))
worsened = sum(1 for sid in v13_by_id if v13_by_id[sid].get('n_matched', 0) < v12_by_id.get(sid, {}).get('num_matched', 0))
same = sum(1 for sid in v13_by_id if v13_by_id[sid].get('n_matched', 0) == v12_by_id.get(sid, {}).get('num_matched', 0))

print(f'Studies improved (more matches): {improved}')
print(f'Studies worsened (fewer matches): {worsened}')
print(f'Studies same: {same}')
print()

# Show the problematic studies (worsened or very different extraction counts)
print('=' * 100)
print('STUDIES THAT WORSENED (V13 < V12 matches)')
print('=' * 100)

for study_id, v13_s in v13_by_id.items():
    v12_s = v12_by_id.get(study_id, {})
    v12_mat = v12_s.get('num_matched', 0)
    v13_mat = v13_s.get('n_matched', 0)
    
    if v13_mat < v12_mat:
        author = v13_s.get('author', study_id)
        print(f"  {author}: V12={v12_mat} matches, V13={v13_mat} matches (lost {v12_mat - v13_mat})")

print()
print('=' * 100)
print('VARIABILITY ANALYSIS')
print('=' * 100)

# Calculate extraction ratio (V13/V12)
ratios = []
for study_id in v13_by_id:
    v12_ext = v12_by_id.get(study_id, {}).get('num_outcomes_extracted', 0)
    v13_ext = v13_by_id[study_id].get('n_extracted', 0)
    if v12_ext > 0:
        ratios.append(v13_ext / v12_ext)

if ratios:
    avg_ratio = sum(ratios) / len(ratios)
    min_ratio = min(ratios)
    max_ratio = max(ratios)
    print(f'V13/V12 extraction ratio:')
    print(f'  Average: {avg_ratio:.2f}x')
    print(f'  Min: {min_ratio:.2f}x')
    print(f'  Max: {max_ratio:.2f}x')
    print()
    print(f'This shows V13 extracts ~{avg_ratio:.1f}x more outcomes than V12 on average')
    print('Reasons:')
    print('  1. Lower dedup threshold (0.55 vs 0.70) keeps more variants')
    print('  2. Prose extraction adds more outcomes')
    print('  3. Both models run in parallel (union not intersection)')
