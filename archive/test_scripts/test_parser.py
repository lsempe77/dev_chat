"""
Test the coefficient/SE parser
"""
from extraction_pipeline.pipeline import parse_cell_comprehensive

test_cases = [
    '0.116* (0.066)',
    '0.033 (0.086)',
    '(0.091) 0.174**',
    '(0.017) [0.052] 0.031**',
    '-0.021 (0.246) [0.933]',
    '3.55***1.132',  # No space - might be issue
    '0.51',
    '0.60 0.69',
    '0.578*** (0.083)',
    '[0.105] -0.031 (0.029)',
]

print('Testing parse_cell_comprehensive:')
print('-'*80)
for cell in test_cases:
    result = parse_cell_comprehensive(cell)
    print('Cell: "{}"'.format(cell))
    print('  Coef: {}, SE: {}, Sig: "{}"'.format(result['coefficient'], result['standard_error'], result['significance']))
    print()
