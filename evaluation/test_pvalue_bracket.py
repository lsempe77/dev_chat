"""Test p-value bracket extraction."""
import sys
sys.path.insert(0, r'c:\Users\LucasSempe\OneDrive - International Initiative for Impact Evaluation\Desktop\Gen AI tools\devchat_v2_sota')

from extraction_pipeline.parsing.cells import parse_cell_comprehensive

# Test cases for the new bracket p-value extraction
test_cases = [
    "0.027 (0.029) [0.347]",  # coef (SE) [p-value]
    "-0.018 (0.047) [0.688]",  # negative coef
    "0.105** (0.052) [0.045]",  # with stars
    "1.234 (0.567)",  # no bracket (should not get p-value)
    "[0.05, 0.15]",  # CI - should NOT extract as p-value
    "[0.123]",  # Just p-value
    "0.5 [1.5]",  # bracket > 1 should NOT be p-value
]

print("Testing p-value extraction from brackets:\n")
for text in test_cases:
    result = parse_cell_comprehensive(text)
    print(f"Text: {text!r}")
    print(f"  coefficient: {result['coefficient']}")
    print(f"  standard_error: {result['standard_error']}")
    print(f"  p_value: {result['p_value']}")
    print(f"  ci_lower: {result['ci_lower']}, ci_upper: {result['ci_upper']}")
    print()
