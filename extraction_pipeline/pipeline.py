"""
Pipeline V2 SOTA: Production-Ready Extraction for Impact Evaluation Papers
==========================================================================

This is a slim orchestration file - all functionality lives in modular components.

Features:
- Stage 1: Metadata extraction (direct from MineRU JSON)
- Stage 2: Table extraction (BeautifulSoup + rules-based filtering)
- Stage 3: LLM classification for ambiguous tables
- Stage 4: Context enrichment (LLM for outcome definitions)

Usage:
    python pipeline.py                    # Extract study 121058356
    python pipeline.py --study_id 12345   # Extract specific study
    python pipeline.py --all              # Extract all studies

Module Structure:
    core/           - LLM client, R2 storage, config, errors
    parsing/        - OCR fixing, cell parsing
    classification/ - Table classification (rules + LLM)
    extraction/     - Table extractors, metadata, prose, sample sizes
    enrichment/     - Outcome classification, analysis types, context
    postprocessing/ - Effect sizes, MinerU cleanup
    batch/          - Batch processing commands
    adapters/       - Schema conversion utilities
"""

import json
import re
import os
import argparse
from typing import Optional, List

import pandas as pd
from bs4 import BeautifulSoup

# ============================================================================
# IMPORTS FROM MODULAR COMPONENTS
# ============================================================================

# Core utilities
from extraction_pipeline.core.storage import get_r2_client, load_mineru_json

# Parsing
from extraction_pipeline.parsing.ocr import fix_ocr_spacing

# Classification
from extraction_pipeline.classification import (
    classify_table_rules,
    classify_table_llm,
    classify_table,
    classify_all_tables_llm,
)

# Extraction
from extraction_pipeline.extraction import (
    detect_table_orientation,
    extract_treatments_in_cols_table,
    extract_outcomes_in_rows_se_split,
    extract_comparison_format_table,
    extract_transposed_table,
    extract_results_table,
    extract_metadata,
    extract_metadata_llm,
    extract_sample_sizes_from_prose,
    extract_effects_from_prose,
    extract_effects_from_figures,
)

# Enrichment
from extraction_pipeline.enrichment import (
    calculate_effect_sizes,
    classify_outcomes,
    classify_analysis_type,
    enrich_with_context,
)

# Adapters (for schema conversion)
from extraction_pipeline.adapters import (
    row_to_extracted_estimate,
    convert_dataframe_to_schema,
)

# ============================================================================
# CONFIGURATION
# ============================================================================

DEFAULT_STUDY_ID = "121058356"
OUTPUT_DIR = "extraction_pipeline/outputs"


# ============================================================================
# MAIN EXTRACTION ORCHESTRATION
# ============================================================================

def extract_all_tables(doc: dict, study_id: str, use_llm: bool = True) -> pd.DataFrame:
    """
    Extract data from all results tables in the document.
    
    Uses two-pass classification when LLM is enabled:
    1. First pass: Build inventory of all tables with captions
    2. Second pass: LLM classifies ALL tables at once (context-aware)
    3. Third pass: Extract only from tables classified as "results"
    """
    tables = doc.get('tables', [])
    all_results = []
    
    print(f"\n  Found {len(tables)} tables in document")
    
    if not tables:
        return pd.DataFrame()
    
    # ========== PASS 1: Build table inventory ==========
    table_inventory = []
    for i, table in enumerate(tables):
        caption_raw = ' '.join(table.get('table_caption', []))
        caption = fix_ocr_spacing(caption_raw)
        html = table.get('table_body', '')
        
        # Get a preview of table content (first 200 chars, cleaned)
        soup = BeautifulSoup(html, 'html.parser')
        preview = soup.get_text(separator=' ', strip=True)[:200]
        
        table_id = f"Table{i+1}"
        table_inventory.append({
            'table_id': table_id,
            'index': i,
            'caption': caption,
            'preview': preview,
            'html': html
        })
    
    # ========== PASS 2: Classify all tables at once ==========
    if use_llm and len(table_inventory) > 0:
        print(f"\n  [SMART CLASSIFICATION] Analyzing {len(table_inventory)} tables...")
        table_classifications = classify_all_tables_llm(table_inventory)
        
        # Show classification summary
        results_tables = [t for t, c in table_classifications.items() if c == 'results']
        descriptive_tables = [t for t, c in table_classifications.items() if c == 'descriptive']
        print(f"    → Results tables: {len(results_tables)} ({', '.join(results_tables[:5])}{'...' if len(results_tables) > 5 else ''})")
        print(f"    → Descriptive tables: {len(descriptive_tables)} (skipped)")
    else:
        # Fallback: use rules-based classification
        table_classifications = {}
        for inv in table_inventory:
            table_classifications[inv['table_id']] = classify_table(inv['caption'], inv['html'], use_llm=False)
    
    # ========== PASS 3: Extract from results tables ==========
    tables_extracted = 0
    tables_skipped = 0
    tables_transposed = 0
    
    for inv in table_inventory:
        i = inv['index']
        table = tables[i]
        caption = inv['caption']
        html = inv['html']
        table_id = inv['table_id']
        
        # Use pre-computed classification
        table_type = table_classifications.get(table_id, 'results')
        
        if table_type == 'results':
            # Detect table orientation
            soup = BeautifulSoup(html, 'html.parser')
            rows = soup.find_all('tr')
            orientation = detect_table_orientation(rows)
            
            # Route to appropriate extractor based on orientation
            results = _extract_by_orientation(orientation, table, study_id)
            
            if results:
                all_results.extend(results)
                orientation_label = f" ({orientation})" if orientation != 'columns' else ""
                print(f"    Table {i}: {caption[:50]}... → {len(results)} rows{orientation_label}")
                tables_extracted += 1
                if orientation != 'columns':
                    tables_transposed += 1
        else:
            tables_skipped += 1
    
    transposed_note = f", {tables_transposed} transposed" if tables_transposed else ""
    print(f"\n  Tables: {tables_extracted} extracted{transposed_note}, {tables_skipped} skipped")
    
    df = pd.DataFrame(all_results)
    
    # P1: Filter suspicious treatment arms and outcome names
    if not df.empty:
        df = _filter_suspicious_rows(df)
    
    return df


def _extract_by_orientation(orientation: str, table: dict, study_id: str) -> Optional[List[dict]]:
    """Route extraction to appropriate function based on table orientation."""
    extractors = {
        'rows': extract_transposed_table,
        'treatments_in_cols': extract_treatments_in_cols_table,
        'outcomes_in_rows_se_split': extract_outcomes_in_rows_se_split,
        'comparison_format': extract_comparison_format_table,
        'columns': extract_results_table,
    }
    
    extractor = extractors.get(orientation, extract_results_table)
    results = extractor(table, study_id)
    
    # Fall back to standard parser if specialized parser fails
    if not results and orientation != 'columns':
        results = extract_results_table(table, study_id)
    
    return results


def _filter_suspicious_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Filter rows that look like metadata, not treatment effects."""
    suspicious_patterns = [
        r'^test\s*:',           # "Test: T1 = T2"
        r'^mean\s+of',          # "Mean of dependent variable"  
        r'^\d+$',               # Pure numbers like "200"
        r'^n\s*=',              # "N = 1234"
        r'^r[\s-]*squared',     # "R-squared"
        r'^observation',        # "Observations"
        r'^control\s+(mean|sd|n)', # Control statistics
        r'^p[\s-]*value',       # "P-value"
        r'^standard\s+error',   # Standard error row
        r'^\*+$',               # Just stars
        r'^note',               # Notes
        r'^source',             # Source
    ]
    
    def is_suspicious(row):
        arm = str(row.get('treatment_arm', '')).lower().strip()
        outcome = str(row.get('outcome_name', '')).lower().strip()
        
        for pattern in suspicious_patterns:
            if re.search(pattern, arm, re.IGNORECASE):
                return True
            if re.search(pattern, outcome, re.IGNORECASE):
                return True
        
        if len(outcome) < 3 or outcome.replace('.', '').isdigit():
            return True
            
        return False
    
    initial_count = len(df)
    df['_suspicious'] = df.apply(is_suspicious, axis=1)
    filtered_count = df['_suspicious'].sum()
    df = df[~df['_suspicious']].drop(columns=['_suspicious'])
    
    if filtered_count > 0:
        print(f"  Filtered {filtered_count} suspicious rows (P1 validation)")
    
    return df


# ============================================================================
# PIPELINE RUNNER
# ============================================================================

def run_pipeline(study_id: str, use_llm: bool = True, enrich: bool = True) -> tuple:
    """Run the full extraction pipeline for a single study."""
    
    print("=" * 70)
    print(f"PIPELINE V2 SOTA: Extracting study {study_id}")
    print("=" * 70)
    
    # Create output directory
    study_output_dir = f"{OUTPUT_DIR}/{study_id}"
    os.makedirs(study_output_dir, exist_ok=True)
    
    # Stage 0: Load data
    print("\n[STAGE 0] Loading MineRU JSON from R2...")
    doc = load_mineru_json(study_id)
    if not doc:
        return None, pd.DataFrame()
    print(f"  ✓ Loaded: {len(doc.get('tables', []))} tables, {len(doc.get('content', ''))} chars")
    
    # Stage 1: Metadata extraction
    print("\n[STAGE 1] Extracting metadata...")
    metadata = _extract_metadata_stage(doc, study_id, use_llm)
    
    with open(f"{study_output_dir}/metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # Stage 2: Table extraction
    print("\n[STAGE 2] Extracting tables (BeautifulSoup + LLM classification)...")
    df = extract_all_tables(doc, study_id, use_llm=use_llm)
    
    # Stage 2b/2c: Fallback extraction from prose/figures
    if df.empty and use_llm:
        df = _fallback_extraction(doc, study_id)
    
    # Add metadata to rows and extract supplementary info
    if not df.empty:
        df = _enrich_with_metadata(df, metadata)
        _print_extraction_stats(df)
        
        # Extract sample sizes from prose if missing
        if use_llm and 'n_treatment' in df.columns and df['n_treatment'].isna().all():
            df = _extract_prose_sample_sizes(df, doc)
    
    # Stage 4-7: Enrichment stages
    if enrich and not df.empty:
        df = _run_enrichment_stages(df, doc)
    
    # Save results
    if not df.empty:
        df.to_csv(f"{study_output_dir}/extracted_data.csv", index=False)
        df.to_json(f"{study_output_dir}/extracted_data.json", orient='records', indent=2)
        print(f"\n  ✓ Saved to {study_output_dir}/")
    
    # Print summary
    _print_final_summary(df)
    
    return metadata, df


def _extract_metadata_stage(doc: dict, study_id: str, use_llm: bool) -> dict:
    """Stage 1: Extract metadata."""
    if use_llm:
        metadata = extract_metadata_llm(doc, study_id)
        print(f"  ✓ Title: {metadata['title'][:60]}...")
        print(f"  ✓ Authors: {str(metadata.get('authors', 'N/A'))[:50]}...")
        print(f"  ✓ Year: {metadata['year']}")
        print(f"  ✓ Country: {metadata.get('country', 'N/A')}")
        print(f"  ✓ Study Design: {metadata.get('study_design', 'N/A')}")
        print(f"  ✓ Follow-up: {metadata.get('follow_up_months', 'N/A')} months")
    else:
        metadata = extract_metadata(doc, study_id)
        print(f"  ✓ Title: {metadata['title'][:60]}...")
        print(f"  ✓ Year: {metadata['year']}")
    return metadata


def _fallback_extraction(doc: dict, study_id: str) -> pd.DataFrame:
    """Stages 2b/2c: Fallback to prose and figure extraction."""
    print("\n[STAGE 2b] No table data - attempting prose extraction...")
    prose_effects = extract_effects_from_prose(doc, study_id)
    if prose_effects:
        print(f"  ✓ Extracted {len(prose_effects)} effects from prose text")
        return pd.DataFrame(prose_effects)
    
    print("  ✗ No effects found in prose either")
    print("\n[STAGE 2c] Attempting figure caption extraction...")
    figure_effects = extract_effects_from_figures(doc, study_id)
    if figure_effects:
        print(f"  ✓ Extracted {len(figure_effects)} effects from figure captions")
        return pd.DataFrame(figure_effects)
    
    print("  ✗ No effects found in figures either")
    return pd.DataFrame()


def _enrich_with_metadata(df: pd.DataFrame, metadata: dict) -> pd.DataFrame:
    """Add study-level metadata to each row."""
    df['authors'] = metadata.get('authors', '')
    df['year'] = metadata.get('year')
    df['country'] = metadata.get('country')
    df['study_design'] = metadata.get('study_design')
    df['is_experimental'] = metadata.get('is_experimental')
    df['follow_up_months'] = metadata.get('follow_up_months')
    df['intervention_name'] = metadata.get('intervention_name')
    return df


def _print_extraction_stats(df: pd.DataFrame):
    """Print extraction statistics."""
    print(f"\n  ✓ Total rows: {len(df)}")
    print(f"  ✓ Unique outcomes: {df['outcome_name'].nunique()}")
    print(f"  ✓ Tables with data: {df['table_number'].nunique()}")
    print(f"  ✓ Coefficient coverage: {100*df['coefficient'].notna().mean():.1f}%")
    print(f"  ✓ SE coverage: {100*df['standard_error'].notna().mean():.1f}%")
    if 'ci_lower' in df.columns:
        print(f"  ✓ CI coverage: {100*df['ci_lower'].notna().mean():.1f}%")


def _extract_prose_sample_sizes(df: pd.DataFrame, doc: dict) -> pd.DataFrame:
    """Extract sample sizes from prose if missing from tables."""
    print("\n[STAGE 3b] Extracting sample sizes from prose...")
    prose_samples = extract_sample_sizes_from_prose(doc)
    if prose_samples.get('n_treatment'):
        df['n_treatment'] = df['n_treatment'].fillna(prose_samples['n_treatment'])
        print(f"  ✓ N treatment from prose: {prose_samples['n_treatment']}")
    if prose_samples.get('n_control'):
        df['n_control'] = df['n_control'].fillna(prose_samples['n_control'])
        print(f"  ✓ N control from prose: {prose_samples['n_control']}")
    if prose_samples.get('n_clusters'):
        df['n_clusters'] = df['n_clusters'].fillna(prose_samples['n_clusters'])
        print(f"  ✓ N clusters from prose: {prose_samples['n_clusters']}")
    return df


def _run_enrichment_stages(df: pd.DataFrame, doc: dict) -> pd.DataFrame:
    """Stages 4-7: Run all enrichment stages."""
    # Stage 4: Context enrichment
    print("\n[STAGE 4] Enriching with LLM context...")
    df = enrich_with_context(df, doc)
    
    # Stage 5: Classify outcomes
    print("\n[STAGE 5] Classifying outcomes...")
    df = classify_outcomes(df, domain='graduation')
    cat_coverage = df['outcome_category'].notna().mean() * 100
    print(f"  ✓ Outcome category coverage: {cat_coverage:.1f}%")
    
    # Stage 6: Calculate effect sizes
    print("\n[STAGE 6] Calculating effect sizes...")
    df = calculate_effect_sizes(df)
    d_coverage = df['cohens_d'].notna().mean() * 100
    g_coverage = df['hedges_g'].notna().mean() * 100
    print(f"  ✓ Cohen's d coverage: {d_coverage:.1f}%")
    print(f"  ✓ Hedges' g coverage: {g_coverage:.1f}%")
    
    # Stage 7: Classify analysis types
    print("\n[STAGE 7] Classifying analysis types (reasoning LLM)...")
    df = classify_analysis_type(df)
    main_pct = df['is_main_effect'].sum() / len(df) * 100
    subgroup_pct = df['is_subgroup'].sum() / len(df) * 100
    spillover_pct = df['is_spillover'].sum() / len(df) * 100
    print(f"  ✓ Main effects: {main_pct:.1f}% of rows")
    print(f"  ✓ Subgroup analyses: {subgroup_pct:.1f}% of rows")
    if subgroup_pct > 0:
        subgroups = df[df['is_subgroup']]['subgroup_variable'].dropna().unique()
        print(f"    Subgroup variables: {', '.join(str(s) for s in subgroups[:5])}")
    print(f"  ✓ Spillover effects: {spillover_pct:.1f}% of rows")
    if spillover_pct > 0:
        spill_types = df[df['is_spillover']]['spillover_type'].dropna().unique()
        print(f"    Spillover types: {', '.join(str(s) for s in spill_types)}")
    
    return df


def _print_final_summary(df: pd.DataFrame):
    """Print final extraction summary."""
    print("\n" + "=" * 70)
    print("EXTRACTION COMPLETE")
    print("=" * 70)
    
    if df.empty:
        return
    
    print("\nFIELD COVERAGE:")
    key_fields = ['coefficient', 'standard_error', 'p_value', 'ci_lower', 'ci_upper',
                  'sample_size', 'n_treatment', 'n_control', 'n_clusters',
                  'control_mean', 'control_sd', 't_statistic',
                  'cohens_d', 'hedges_g', 'effect_variance', 'effect_se',
                  'outcome_category', 'authors', 'year', 'country', 'study_design',
                  'follow_up_months', 'is_experimental']
    for field in key_fields:
        if field in df.columns:
            cov = df[field].notna().mean() * 100
            print(f"  {field:20}: {cov:5.1f}%")
    
    if 'is_main_effect' in df.columns:
        print("\nANALYSIS TYPE CLASSIFICATION:")
        print(f"  Main effects:      {df['is_main_effect'].sum():4} rows ({100*df['is_main_effect'].mean():.1f}%)")
        print(f"  Subgroup analyses: {df['is_subgroup'].sum():4} rows ({100*df['is_subgroup'].mean():.1f}%)")
        print(f"  Spillover effects: {df['is_spillover'].sum():4} rows ({100*df['is_spillover'].mean():.1f}%)")
        print(f"  Cost outcomes:     {df['is_cost_outcome'].sum():4} rows ({100*df['is_cost_outcome'].mean():.1f}%)")
        print(f"  Mechanism/mediator:{df['is_mechanism'].sum():4} rows ({100*df['is_mechanism'].mean():.1f}%)")


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Extract impact evaluation data from papers')
    parser.add_argument('--study_id', type=str, default=DEFAULT_STUDY_ID, help='Study ID to extract')
    parser.add_argument('--no-llm', action='store_true', help='Disable LLM classification')
    parser.add_argument('--no-enrich', action='store_true', help='Disable LLM enrichment')
    
    args = parser.parse_args()
    
    metadata, df = run_pipeline(
        study_id=args.study_id,
        use_llm=not args.no_llm,
        enrich=not args.no_enrich
    )
    
    if not df.empty:
        print(f"\nSample output:")
        print(df[['table_number', 'treatment_arm', 'outcome_name', 'coefficient', 'standard_error']].head(10).to_string())


if __name__ == "__main__":
    main()
