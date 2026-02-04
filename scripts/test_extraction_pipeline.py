"""
Test extraction pipeline components against real data.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from extraction_pipeline.parsing.cells import parse_coefficient_se
from extraction_pipeline.pipeline import classify_table_rules


def test_extraction_pipeline():
    print("=" * 60)
    print("TEST: Extraction Pipeline Components")
    print("=" * 60)

    # Test 1: Coefficient/SE parsing (now includes p_value)
    print("\n1. PARSING COEFFICIENT + SE")
    test_cells = [
        ("0.15*** (0.05)", 0.15, 0.05, "***", 0.001),
        ("-0.23** (0.12)", -0.23, 0.12, "**", 0.01),
        ("0.08 (0.03)", 0.08, 0.03, "", None),
        ("1.45***", 1.45, None, "***", 0.001),
        ("", None, None, None, None),
    ]
    
    parse_passed = 0
    for cell, exp_coef, exp_se, exp_sig, exp_pval in test_cells:
        coef, se, sig, p_value, p_value_text = parse_coefficient_se(cell)
        match = (coef == exp_coef) and (se == exp_se) and (sig == exp_sig)
        # Also check p_value mapping
        pval_match = (p_value == exp_pval)
        status = "✅" if (match and pval_match) else "❌"
        print(f'  {status} "{cell}" -> coef={coef}, se={se}, sig="{sig}", p_value={p_value}')
        if match:
            parse_passed += 1
    
    print(f"  Parsing: {parse_passed}/{len(test_cells)} passed")

    # Test 2: Table classification (rules-based)
    print("\n2. TABLE CLASSIFICATION (rules)")
    test_captions = [
        ("Table 1: Treatment Effects on Consumption", "results"),
        ("Table A5: Variable Definitions", "descriptive"),
        ("Table 2: Balance Test", "descriptive"),
        ("Figure 3: Timeline", "figure"),
        ("", "unknown"),
    ]
    
    class_passed = 0
    for cap, expected in test_captions:
        result = classify_table_rules(cap)
        match = result == expected
        status = "✅" if match else "❌"
        print(f'  {status} "{cap[:35]}..." -> {result} (expected: {expected})')
        if match:
            class_passed += 1
    
    print(f"  Classification: {class_passed}/{len(test_captions)} passed")

    # Test 3: Check actual extraction output quality
    print("\n3. EXTRACTION OUTPUT QUALITY (Study 121058356)")
    df = pd.read_csv("extraction_pipeline/outputs/121058356/extracted_data.csv")
    
    stats = {
        "Total rows": len(df),
        "With coefficients": df["coefficient"].notna().sum(),
        "With SE": df["standard_error"].notna().sum(),
        "With significance": df["significance"].notna().sum(),
        "Unique tables": df["table_number"].nunique(),
        "Unique outcomes": df["outcome_name"].nunique(),
    }
    
    for key, val in stats.items():
        print(f"  {key}: {val}")
    
    # Check coverage
    coef_coverage = stats["With coefficients"] / stats["Total rows"] * 100
    se_coverage = stats["With SE"] / stats["Total rows"] * 100
    sig_coverage = stats["With significance"] / stats["Total rows"] * 100
    
    print(f"\n  Coverage rates:")
    print(f"    Coefficient: {coef_coverage:.1f}%")
    print(f"    SE: {se_coverage:.1f}%")
    print(f"    Significance: {sig_coverage:.1f}%")
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    all_passed = (parse_passed == len(test_cells)) and (class_passed == len(test_captions))
    print(f"  Parsing tests: {parse_passed}/{len(test_cells)}")
    print(f"  Classification tests: {class_passed}/{len(test_captions)}")
    print(f"  Extraction output: {stats['Total rows']} rows from {stats['Unique tables']} tables")
    
    if all_passed:
        print("\n✅ All pipeline tests PASSED")
    else:
        print("\n⚠️ Some tests failed")
    
    return all_passed


if __name__ == "__main__":
    test_extraction_pipeline()
