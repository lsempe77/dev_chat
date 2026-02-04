"""
Test extraction schemas against real ground truth data.
"""

import pandas as pd
from src.extraction.schemas import (
    CoreNumericFields, StudyMetadata, OutcomeMetadata, SourceLocation,
    ExtractionMode, DOMAIN_CONFIGS, get_domain_config, list_available_domains, 
    EXTRACTION_FIELDS
)


def test_with_ground_truth():
    """Test parsing real ground truth data into extraction schemas."""
    print("=" * 60)
    print("TEST: Extraction Schemas with Ground Truth Data")
    print("=" * 60)
    
    # Load ground truth
    df = pd.read_excel("data/8WR QEX Combined.xlsx")
    print(f"\nLoaded {len(df)} rows from 8WR QEX Combined.xlsx")
    
    # Map GT columns to our schema
    # GT uses: 'Coeff reg', 'SE reg\xa0', 'N total\xa0', 'Outcome name', 'Source'
    col_map = {
        "effect_estimate": "Coeff reg",
        "standard_error": "SE reg\xa0",  # Note: has special whitespace
        "n_total": "N total\xa0",
        "outcome_name": "Outcome name",
        "table_reference": "Source",
    }
    
    # Find rows with actual effect sizes
    es_col = col_map["effect_estimate"]
    df_with_es = df[df[es_col].notna()]
    print(f"Rows with effect sizes: {len(df_with_es)}")
    
    if len(df_with_es) == 0:
        print("\nNo rows with effect sizes found")
        return False
    
    # Test with 5 sample rows
    print("\n--- Testing 5 sample rows ---")
    success_count = 0
    
    for i, (_, row) in enumerate(df_with_es.head(5).iterrows()):
        try:
            # Parse core numeric fields
            numeric = CoreNumericFields(
                effect_estimate=float(row[col_map["effect_estimate"]]) if pd.notna(row[col_map["effect_estimate"]]) else None,
                standard_error=float(row[col_map["standard_error"]]) if pd.notna(row[col_map["standard_error"]]) else None,
                n_total=int(row[col_map["n_total"]]) if pd.notna(row[col_map["n_total"]]) else None,
            )
            
            # Parse outcome metadata
            outcome = OutcomeMetadata(
                outcome_name=str(row.get(col_map["outcome_name"], "")) if pd.notna(row.get(col_map["outcome_name"])) else None,
            )
            
            # Parse source location
            source = SourceLocation(
                table_number=str(row.get(col_map["table_reference"], "")) if pd.notna(row.get(col_map["table_reference"])) else None,
            )
            
            es_val = numeric.effect_estimate
            es_str = f"{es_val:.4f}" if es_val is not None else "None"
            print(f"  ✅ Row {i+1}: effect={es_str}, "
                  f"se={numeric.standard_error}, n={numeric.n_total}, "
                  f"outcome={outcome.outcome_name[:30] if outcome.outcome_name else 'None'}...")
            success_count += 1
            
        except Exception as e:
            print(f"  ❌ Row {i+1}: {e}")
    
    print(f"\n--- Results: {success_count}/5 rows parsed successfully ---")
    
    # Test domain configs
    print("\n--- Domain Configurations ---")
    domains = list_available_domains()
    print(f"Available domains: {domains}")
    
    for domain in ["graduation", "education", "health"]:
        config = get_domain_config(domain)
        print(f"  {domain}: {len(config.get('outcome_categories', []))} outcome categories")
    
    # Test extraction modes
    print("\n--- Extraction Modes ---")
    for mode in ExtractionMode:
        fields = EXTRACTION_FIELDS.get(mode, [])
        print(f"  {mode.value}: {len(fields)} fields")
    
    return success_count > 0


if __name__ == "__main__":
    success = test_with_ground_truth()
    print(f"\n{'✅ Schema test PASSED' if success else '❌ Schema test FAILED'}")
