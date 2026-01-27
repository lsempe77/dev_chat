"""Comprehensive categorization of ALL ground truth columns for extraction planning."""
import pandas as pd

qex = pd.read_excel('data/8WR QEX Combined.xlsx', sheet_name='Sheet1')
om = pd.read_excel('data/8 week SR OM Combined.xlsx', sheet_name='OM for 50 studies')

print("=" * 100)
print("COMPLETE COLUMN CATEGORIZATION FOR EXTRACTION PIPELINE")
print("=" * 100)
print(f"\nTotal QEX columns: {len(qex.columns)}")
print(f"Total OM columns: {len(om.columns)}")

# Categorize columns by extraction source
categories = {
    "EXTRACTED_FROM_PAPER_CORE": [],      # Must extract from PDF
    "EXTRACTED_FROM_PAPER_METADATA": [],   # Study metadata from PDF
    "EXTRACTED_FROM_TABLES": [],           # Table-specific extractions
    "CALCULATED_DERIVED": [],              # Calculated from extracted values
    "CODED_MANUALLY": [],                  # Human judgment required
    "SELECTION_FLAGS_RVE": [],             # For meta-analysis selection
    "ADMIN_INTERNAL": [],                  # Coder notes, IDs
}

# Define categorization
core_numeric = ['Coeff reg', 'SE reg ', 'Tstat reg ', 'CI_LB reg ', 'CI_UP reg ', 
                'P value exact ', 'N treatment', 'N control', 'N total ',
                'Clusters treatment ', 'Clusters control ', 'Clusters total ', '# of periods']

study_metadata = ['StudyID', 'EstimateID', 'Author name', 'Year of publication', 'Country',
                  'Intervention abbreviation and name', 'full Intervention country abbreviation',
                  'Name', 'program_id', 'program_name']

outcome_metadata = ['Outcome category', 'Outcome name', 'Outcome description', 
                    'Length of follow up', 'Treatment', 'Source', 'treat_arm']

intervention_components = ['Consumption support (cash or in-kind) to stabilize food security and prevent households from selling assets to survive',
                          'health_comp', 'Assets transfer (often livestock, tools, or seed capital) to provide a foundation for an income-generation activity.',
                          'skills_comp', 'savings_comp', 'coaching_comp', 'social_comp']

study_design = ['experimental', 'Exposure to intervention', 'Reverse sign',
                'Does the sample size need to be corrected? ', 'n_T_revised', 'Formula Used',
                'cash_control', 'cash_control_desc', 'targeting_women', 'targeting_women_desc',
                'uoa_analysis_needed', 'uoa_analysis_needed_desc']

calculated_es = ['d', 'd_rev', 'yi', 'var(d)', 'j adjustment', 'vi', 'se(g)', 'CI_l', 'CI_u']

geography = ['continent_all', 'continent_ssa', 'continent_southa', 'continent_mena', 
             'continent_lac', 'continent_eap']

admin = ['Coder name', 'Notes']

# RVE selection flags (these are meta-analysis specific selections)
rve_flags = [col for col in qex.columns if 'selected_rve' in col.lower() or 'selected_re' in col.lower()
             or col.startswith('inc_') or col == 'Income']

print("\n" + "=" * 100)
print("CATEGORY BREAKDOWN")
print("=" * 100)

def print_category(name, cols, qex_df):
    print(f"\n### {name} ###")
    found = [c for c in cols if c in qex_df.columns]
    not_found = [c for c in cols if c not in qex_df.columns]
    for col in found:
        filled = qex_df[col].notna().sum()
        pct = filled / len(qex_df) * 100
        sample = qex_df[col].dropna().iloc[0] if filled > 0 else "N/A"
        if isinstance(sample, str) and len(sample) > 40:
            sample = sample[:40] + "..."
        print(f"  {col[:55]:55s} | {filled:4d} ({pct:5.1f}%) | {str(sample)[:40]}")
    if not_found:
        print(f"  NOT FOUND: {not_found}")
    return found

print_category("1. CORE NUMERIC (Extract from tables)", core_numeric, qex)
print_category("2. STUDY METADATA (Extract from paper)", study_metadata, qex)
print_category("3. OUTCOME METADATA (Extract from paper)", outcome_metadata, qex)
print_category("4. INTERVENTION COMPONENTS (Coded)", intervention_components, qex)
print_category("5. STUDY DESIGN (Coded/Extract)", study_design, qex)
print_category("6. CALCULATED EFFECT SIZES (Derived)", calculated_es, qex)
print_category("7. GEOGRAPHY (Derived)", geography, qex)
print_category("8. ADMIN (Internal)", admin, qex)

print(f"\n### 9. RVE SELECTION FLAGS ({len(rve_flags)} columns) ###")
print("  These are meta-analysis selection indicators - NOT extracted from papers")
for col in rve_flags[:10]:
    filled = qex[col].notna().sum()
    pct = filled / len(qex) * 100
    print(f"  {col[:55]:55s} | {filled:4d} ({pct:5.1f}%)")
print(f"  ... and {len(rve_flags) - 10} more RVE columns")

# Identify uncategorized columns
all_categorized = (core_numeric + study_metadata + outcome_metadata + 
                   intervention_components + study_design + calculated_es + 
                   geography + admin + rve_flags)
uncategorized = [c for c in qex.columns if c not in all_categorized]
if uncategorized:
    print(f"\n### UNCATEGORIZED ({len(uncategorized)} columns) ###")
    for col in uncategorized:
        filled = qex[col].notna().sum()
        pct = filled / len(qex) * 100
        print(f"  {col[:55]:55s} | {filled:4d} ({pct:5.1f}%)")

print("\n" + "=" * 100)
print("OM FILE - LOCATION & TABLE METADATA")
print("=" * 100)

for col in om.columns:
    filled = om[col].notna().sum()
    pct = filled / len(om) * 100
    sample = om[col].dropna().iloc[0] if filled > 0 else "N/A"
    if isinstance(sample, str) and len(sample) > 60:
        sample = sample[:60] + "..."
    print(f"  {col[:55]:55s} | {filled:4d} ({pct:5.1f}%) | {str(sample)[:50]}")

print("\n" + "=" * 100)
print("EXTRACTION PIPELINE REQUIREMENTS SUMMARY")
print("=" * 100)

print("""
USE CASE 1: RAG SYNTHESIS (DevChat)
===================================
Needs: Quick extraction of key findings for conversational AI
- Core effect sizes (Coeff, SE, p-value, N)
- Study metadata (Author, Year, Country, Intervention)
- Outcome descriptions
- Key findings summary

USE CASE 2: SYSTEMATIC REVIEW EXTRACTION
========================================
Needs: Complete data extraction matching QEX template
- ALL core numeric fields (13 columns)
- ALL study metadata (10 columns)
- ALL outcome metadata (7 columns)
- Intervention components (7 columns) - may need coding
- Study design fields (12 columns) - partially extractable
- Location data from OM file

AUTOMATION POTENTIAL:
====================
""")

# Calculate automation potential
extractable = len(core_numeric) + len(study_metadata) + len(outcome_metadata)
coded = len(intervention_components) + len([c for c in study_design if 'desc' not in c])
derived = len(calculated_es) + len(geography)
selection = len(rve_flags)

print(f"  Directly extractable from PDF:  {extractable} columns")
print(f"  Requires human coding:          {coded} columns")
print(f"  Can be calculated/derived:      {derived} columns")
print(f"  Meta-analysis selection flags:  {selection} columns (human decision)")
print(f"  Admin/internal:                 {len(admin)} columns")
