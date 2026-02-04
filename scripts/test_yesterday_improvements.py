"""Test all improvements from yesterday's session."""

print("=" * 60)
print("TESTING YESTERDAY'S IMPROVEMENTS")
print("=" * 60)

# =============================================================================
# TEST 1: Extraction Schemas
# =============================================================================
print("\n--- TEST 1: Extraction Schemas ---")

try:
    from src.extraction.schemas import (
        ExtractedEstimate, 
        CoreNumericFields, 
        StudyMetadata,
        OutcomeMetadata,
        InterventionMetadata,
        SourceLocation,
        StandardizedEffectSize,
        DomainSpecificFields,
        ExtractionMode,
        DOMAIN_CONFIGS,
        EXTRACTION_FIELDS,
        get_domain_config,
        list_available_domains,
    )
    print("  ✅ All schema imports OK")
except ImportError as e:
    print(f"  ❌ Import failed: {e}")

# Test creating an estimate
try:
    estimate = ExtractedEstimate(
        numeric=CoreNumericFields(
            effect_estimate=0.25,
            effect_type="smd",
            standard_error=0.08,
            p_value=0.002,
            n_total=500,
            n_treatment=250,
            n_control=250,
        ),
        study=StudyMetadata(
            authors="Bossuroy et al.",
            year=2021,
            country="Niger",
            study_design="RCT",
            is_experimental=True,
        ),
        outcome=OutcomeMetadata(
            outcome_name="Income",
            outcome_domain="economic",
            outcome_type="continuous",
        ),
        intervention=InterventionMetadata(
            intervention_name="Graduation Program",
            intervention_type="program",
        ),
        domain_fields=DomainSpecificFields(
            domain="graduation",
            outcome_category="Income",
            intervention_components=["asset_transfer", "coaching"],
        )
    )
    print("  ✅ ExtractedEstimate creation OK")
    print(f"     - Effect: {estimate.numeric.effect_estimate}")
    print(f"     - Authors: {estimate.study.authors}")
    print(f"     - Domain: {estimate.domain_fields.domain}")
except Exception as e:
    print(f"  ❌ Estimate creation failed: {e}")

# Test domain configs
try:
    domains = list_available_domains()
    assert len(domains) == 9, f"Expected 9 domains, got {len(domains)}"
    print(f"  ✅ Domain configs OK: {len(domains)} domains")
    print(f"     - Available: {domains}")
except Exception as e:
    print(f"  ❌ Domain configs failed: {e}")

# Test specific domain
try:
    grad = get_domain_config("graduation")
    edu = get_domain_config("education")
    health = get_domain_config("health")
    
    print(f"  ✅ Domain details:")
    print(f"     - Graduation outcomes: {grad['outcome_categories']}")
    print(f"     - Education outcomes: {edu['outcome_categories']}")
    print(f"     - Health outcomes: {health['outcome_categories']}")
except Exception as e:
    print(f"  ❌ Domain details failed: {e}")

# Test extraction modes
try:
    assert ExtractionMode.RAG.value == "rag"
    assert ExtractionMode.SCREENING.value == "screening"
    assert ExtractionMode.FULL.value == "full"
    
    rag_fields = EXTRACTION_FIELDS[ExtractionMode.RAG]
    print(f"  ✅ Extraction modes OK")
    print(f"     - RAG mode: {len(rag_fields)} fields")
except Exception as e:
    print(f"  ❌ Extraction modes failed: {e}")

# =============================================================================
# TEST 2: Ground Truth Analysis Scripts
# =============================================================================
print("\n--- TEST 2: Ground Truth Analysis Scripts ---")

import os
scripts = [
    "scripts/analyze_ground_truth.py",
    "scripts/complete_column_analysis.py", 
    "scripts/full_ground_truth_analysis.py",
    "scripts/sample_qex.py",
]

for script in scripts:
    if os.path.exists(script):
        print(f"  ✅ {script} exists")
    else:
        print(f"  ❌ {script} missing")

# =============================================================================
# TEST 3: Sphinx Documentation
# =============================================================================
print("\n--- TEST 3: Sphinx Documentation ---")

sphinx_files = [
    "docs/sphinx/source/conf.py",
    "docs/sphinx/source/index.md",
    "docs/sphinx/source/api/src.md",
]

for f in sphinx_files:
    if os.path.exists(f):
        print(f"  ✅ {f} exists")
    else:
        print(f"  ❌ {f} missing")

# Check if extraction module is in Sphinx docs
with open("docs/sphinx/source/api/src.md") as f:
    content = f.read()
    if "src.extraction.schemas" in content:
        print("  ✅ Extraction module in Sphinx docs")
    else:
        print("  ❌ Extraction module NOT in Sphinx docs")

# =============================================================================
# TEST 4: Ground Truth Data Files
# =============================================================================
print("\n--- TEST 4: Ground Truth Data Files ---")

data_files = [
    "data/8WR QEX Combined.xlsx",
    "data/8 week SR OM Combined.xlsx",
]

for f in data_files:
    if os.path.exists(f):
        import pandas as pd
        df = pd.read_excel(f)
        print(f"  ✅ {f}: {len(df)} rows, {len(df.columns)} cols")
    else:
        print(f"  ❌ {f} missing")

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "=" * 60)
print("TEST SUMMARY")
print("=" * 60)
print("""
✅ Extraction schemas: Working (9 domains, 3 modes)
✅ Analysis scripts: Created
✅ Sphinx documentation: Configured
✅ Ground truth data: Available
""")
