"""
Pipeline CLI - Main Entry Point
===============================

Improved CLI with:
- Clear stage boundaries
- Comprehensive CLI flags
- Final summary statistics
- Error accumulation and reporting
- Multi-tenant project support
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Optional, Tuple
from pathlib import Path

import pandas as pd
from loguru import logger
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure loguru
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    level="INFO",
)

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from extraction_pipeline.core.config import PipelineConfig, ExtractionMode, ColumnNames
from extraction_pipeline.core.errors import (
    ErrorAccumulator, 
    ExtractionStage, 
    set_accumulator,
    reset_accumulator,
)
from extraction_pipeline.core.storage import (
    load_mineru_json, 
    list_available_studies, 
    list_projects,
    DEFAULT_PROJECT_ID,
)
from extraction_pipeline.core.llm_client import get_llm_client, get_cache
from extraction_pipeline.adapters import convert_dataframe_to_schema, validate_dataframe_columns
from extraction_pipeline.postprocessing import calculate_effect_sizes, summarize_effect_sizes


def print_banner(study_id: str, config: PipelineConfig) -> None:
    """Print pipeline banner with configuration."""
    print("=" * 70)
    print(f"EXTRACTION PIPELINE V2")
    print(f"Study: {study_id}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 70)
    print(config.summary())
    print("=" * 70)


def print_stage(stage_num: int, name: str, description: str = "") -> None:
    """Print stage header."""
    print(f"\n[STAGE {stage_num}] {name}")
    if description:
        print(f"  {description}")


def print_summary(
    study_id: str,
    df: pd.DataFrame,
    metadata: dict,
    accumulator: ErrorAccumulator,
    elapsed_seconds: float,
    config: PipelineConfig,
) -> None:
    """Print comprehensive extraction summary."""
    print("\n" + "=" * 70)
    print("EXTRACTION COMPLETE")
    print("=" * 70)
    
    # Basic stats
    print(f"\nStudy: {study_id}")
    print(f"Elapsed: {elapsed_seconds:.1f}s")
    print(f"Rows extracted: {len(df)}")
    
    if not df.empty:
        print(f"Unique outcomes: {df[ColumnNames.OUTCOME_NAME].nunique()}")
        print(f"Unique tables: {df[ColumnNames.TABLE_NUMBER].nunique()}")
    
    # Field coverage
    if not df.empty:
        print("\nFIELD COVERAGE:")
        key_fields = [
            (ColumnNames.COEFFICIENT, "Coefficient"),
            (ColumnNames.STANDARD_ERROR, "Standard Error"),
            (ColumnNames.P_VALUE, "P-value"),
            (ColumnNames.CI_LOWER, "CI bounds"),
            (ColumnNames.SAMPLE_SIZE, "Sample size"),
            (ColumnNames.N_TREATMENT, "N treatment"),
            (ColumnNames.N_CONTROL, "N control"),
            (ColumnNames.CONTROL_MEAN, "Control mean"),
            (ColumnNames.CONTROL_SD, "Control SD"),
            (ColumnNames.COHENS_D, "Cohen's d"),
            (ColumnNames.HEDGES_G, "Hedges' g"),
        ]
        for col, label in key_fields:
            if col in df.columns:
                coverage = df[col].notna().mean() * 100
                print(f"  {label:20}: {coverage:5.1f}%")
    
    # Effect size summary
    if not df.empty and ColumnNames.COHENS_D in df.columns:
        es_summary = summarize_effect_sizes(df)
        if es_summary["n_calculated"] > 0:
            print("\nEFFECT SIZE SUMMARY:")
            print(f"  Calculated: {es_summary['n_calculated']} ({es_summary['coverage_pct']:.1f}%)")
            print(f"  Mean Cohen's d: {es_summary['mean_d']:.3f}" if es_summary['mean_d'] else "")
            print(f"  Mean Hedges' g: {es_summary['mean_g']:.3f}" if es_summary['mean_g'] else "")
            if es_summary["assumption_breakdown"]:
                print("  Assumptions:")
                for assumption, count in es_summary["assumption_breakdown"].items():
                    print(f"    - {assumption}: {count} rows")
    
    # Analysis type breakdown
    if not df.empty and ColumnNames.IS_MAIN_EFFECT in df.columns:
        print("\nANALYSIS TYPE CLASSIFICATION:")
        main_pct = df[ColumnNames.IS_MAIN_EFFECT].mean() * 100 if ColumnNames.IS_MAIN_EFFECT in df.columns else 0
        subgroup_pct = df[ColumnNames.IS_SUBGROUP].mean() * 100 if ColumnNames.IS_SUBGROUP in df.columns else 0
        spillover_pct = df[ColumnNames.IS_SPILLOVER].mean() * 100 if ColumnNames.IS_SPILLOVER in df.columns else 0
        print(f"  Main effects: {main_pct:.1f}%")
        print(f"  Subgroups:    {subgroup_pct:.1f}%")
        print(f"  Spillovers:   {spillover_pct:.1f}%")
    
    # LLM statistics
    if config.is_llm_enabled:
        llm_client = get_llm_client()
        cache = get_cache()
        print("\nLLM STATISTICS:")
        print(f"  Total calls: {llm_client.call_count}")
        print(f"  Avg latency: {llm_client.average_latency_ms:.0f}ms")
        print(f"  Cache hit rate: {cache.hit_rate*100:.1f}%")
        print(f"  Success rate: {accumulator.llm_success_rate*100:.1f}%")
    
    # Errors and warnings
    print(f"\nISSUES:")
    print(f"  Errors:   {accumulator.error_count}")
    print(f"  Warnings: {accumulator.warning_count}")
    
    if accumulator.has_errors:
        print("\n  Recent errors:")
        for err in accumulator.errors[:5]:
            print(f"    - [{err.stage.value}] {err.message}")


def run_pipeline_v2(
    study_id: str,
    config: Optional[PipelineConfig] = None,
    project_id: str = DEFAULT_PROJECT_ID,
) -> Tuple[Optional[dict], pd.DataFrame]:
    """
    Run extraction pipeline with improved structure.
    
    Args:
        study_id: Study ID to extract
        config: Pipeline configuration (uses defaults if None)
        project_id: RAG project UUID for multi-tenant support
        
    Returns:
        Tuple of (metadata dict, results DataFrame)
    """
    config = config or PipelineConfig()
    start_time = time.time()
    
    # Initialize error accumulator
    accumulator = ErrorAccumulator(study_id=study_id, strict=config.strict_mode)
    set_accumulator(accumulator)
    
    # Print banner
    print_banner(study_id, config)
    
    # Create output directory
    output_dir = Path(config.output_dir) / study_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # =========================================================================
    # STAGE 0: Load Document
    # =========================================================================
    print_stage(0, "Load Document", "Loading MineRU JSON from R2 storage")
    
    doc = load_mineru_json(study_id, project_id=project_id)
    if not doc:
        accumulator.error(
            message=f"Failed to load document for study {study_id}",
            stage=ExtractionStage.LOADING,
            recoverable=False,
        )
        return None, pd.DataFrame()
    
    table_count = len(doc.get('tables', []))
    content_len = len(doc.get('content', ''))
    print(f"  ✓ Loaded: {table_count} tables, {content_len:,} chars")
    
    # =========================================================================
    # STAGE 1: Metadata Extraction
    # =========================================================================
    print_stage(1, "Metadata Extraction")
    
    # Import from original pipeline for now
    # TODO: Move metadata extraction to separate module
    from extraction_pipeline.pipeline import extract_metadata, extract_metadata_llm
    
    if config.use_llm_metadata:
        metadata = extract_metadata_llm(doc, study_id)
    else:
        metadata = extract_metadata(doc, study_id)
    
    print(f"  ✓ Title: {metadata.get('title', 'N/A')[:60]}...")
    print(f"  ✓ Authors: {str(metadata.get('authors', 'N/A'))[:50]}...")
    print(f"  ✓ Year: {metadata.get('year', 'N/A')}")
    if config.use_llm_metadata:
        print(f"  ✓ Country: {metadata.get('country', 'N/A')}")
        print(f"  ✓ Design: {metadata.get('study_design', 'N/A')}")
    
    # Save metadata
    with open(output_dir / "metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2, default=str)
    
    # =========================================================================
    # STAGE 2: Table Extraction
    # =========================================================================
    print_stage(2, "Table Extraction", "Parsing tables with BeautifulSoup + classification")
    
    from extraction_pipeline.pipeline import extract_all_tables
    
    df = extract_all_tables(doc, study_id, use_llm=config.use_llm_classification)
    
    if not df.empty:
        print(f"  ✓ Extracted {len(df)} rows from {df[ColumnNames.TABLE_NUMBER].nunique()} tables")
    else:
        print("  ⚠ No table data extracted")
    
    # =========================================================================
    # STAGE 2b: Prose Fallback
    # =========================================================================
    if df.empty and config.use_prose_extraction:
        print_stage("2b", "Prose Extraction", "Fallback: extracting from prose text")
        
        from extraction_pipeline.pipeline import extract_effects_from_prose
        
        prose_effects = extract_effects_from_prose(doc, study_id)
        if prose_effects:
            df = pd.DataFrame(prose_effects)
            print(f"  ✓ Extracted {len(df)} effects from prose")
        else:
            print("  ⚠ No effects found in prose")
    
    # =========================================================================
    # STAGE 2c: Figure Fallback
    # =========================================================================
    if df.empty and config.use_figure_extraction:
        print_stage("2c", "Figure Extraction", "Fallback: extracting from figure captions")
        
        from extraction_pipeline.pipeline import extract_effects_from_figures
        
        figure_effects = extract_effects_from_figures(doc, study_id)
        if figure_effects:
            df = pd.DataFrame(figure_effects)
            print(f"  ✓ Extracted {len(df)} effects from figures")
        else:
            print("  ⚠ No effects found in figures")
    
    if df.empty:
        print("\n  ✗ No data extracted from any source")
        elapsed = time.time() - start_time
        print_summary(study_id, df, metadata, accumulator, elapsed, config)
        return metadata, df
    
    # =========================================================================
    # STAGE 3: Add Study Metadata
    # =========================================================================
    print_stage(3, "Merge Metadata", "Adding study-level fields to each row")
    
    # Add metadata fields to each row
    # Handle authors - can be list, string, or None
    authors = metadata.get('authors', '')
    if isinstance(authors, list):
        authors = '; '.join(str(a) for a in authors) if authors else ''
    df[ColumnNames.AUTHORS] = authors
    
    df[ColumnNames.YEAR] = metadata.get('year')
    df[ColumnNames.COUNTRY] = metadata.get('country')
    df[ColumnNames.STUDY_DESIGN] = metadata.get('study_design')
    df[ColumnNames.IS_EXPERIMENTAL] = metadata.get('is_experimental')
    df[ColumnNames.FOLLOW_UP_MONTHS] = metadata.get('follow_up_months')
    df[ColumnNames.INTERVENTION_NAME] = metadata.get('intervention_name')
    
    print(f"  ✓ Added {7} metadata fields to {len(df)} rows")
    
    # =========================================================================
    # STAGE 4: Sample Size Enrichment
    # =========================================================================
    if config.use_sample_size_prose and df[ColumnNames.N_TREATMENT].isna().all():
        print_stage(4, "Sample Size Enrichment", "Extracting sample sizes from prose")
        
        from extraction_pipeline.pipeline import extract_sample_sizes_from_prose
        
        prose_samples = extract_sample_sizes_from_prose(doc)
        if prose_samples.get('n_treatment'):
            df[ColumnNames.N_TREATMENT] = df[ColumnNames.N_TREATMENT].fillna(prose_samples['n_treatment'])
            print(f"  ✓ N treatment: {prose_samples['n_treatment']}")
        if prose_samples.get('n_control'):
            df[ColumnNames.N_CONTROL] = df[ColumnNames.N_CONTROL].fillna(prose_samples['n_control'])
            print(f"  ✓ N control: {prose_samples['n_control']}")
    
    # =========================================================================
    # STAGE 5: Context Enrichment
    # =========================================================================
    if config.use_context_enrichment:
        print_stage(5, "Context Enrichment", "LLM enrichment for outcome definitions")
        
        from extraction_pipeline.pipeline import enrich_with_context
        
        df = enrich_with_context(df, doc)
        print(f"  ✓ Enriched {len(df)} rows")
    
    # =========================================================================
    # STAGE 6: Outcome Classification
    # =========================================================================
    if config.use_outcome_classification:
        print_stage(6, "Outcome Classification", f"Classifying into {config.domain} categories")
        
        from extraction_pipeline.pipeline import classify_outcomes
        
        df = classify_outcomes(df, domain=config.domain)
        coverage = df[ColumnNames.OUTCOME_CATEGORY].notna().mean() * 100
        print(f"  ✓ Category coverage: {coverage:.1f}%")
    
    # =========================================================================
    # STAGE 7: Effect Size Calculation
    # =========================================================================
    if config.calculate_effect_sizes:
        print_stage(7, "Effect Size Calculation", "Cohen's d, Hedges' g with assumptions")
        
        df = calculate_effect_sizes(df, require_minimum_inputs=True)
        
        d_coverage = df[ColumnNames.COHENS_D].notna().mean() * 100
        g_coverage = df[ColumnNames.HEDGES_G].notna().mean() * 100
        print(f"  ✓ Cohen's d coverage: {d_coverage:.1f}%")
        print(f"  ✓ Hedges' g coverage: {g_coverage:.1f}%")
    
    # =========================================================================
    # STAGE 8: Analysis Type Classification
    # =========================================================================
    if config.use_analysis_classification:
        print_stage(8, "Analysis Classification", "Detecting subgroups, spillovers, mechanisms")
        
        from extraction_pipeline.pipeline import classify_analysis_type
        
        df = classify_analysis_type(df)
        
        main_pct = df[ColumnNames.IS_MAIN_EFFECT].mean() * 100
        subgroup_pct = df[ColumnNames.IS_SUBGROUP].mean() * 100
        print(f"  ✓ Main effects: {main_pct:.1f}%")
        print(f"  ✓ Subgroups: {subgroup_pct:.1f}%")
    
    # =========================================================================
    # STAGE 9: Validation & Output
    # =========================================================================
    print_stage(9, "Validation & Output", "Validating schema and saving results")
    
    # Validate columns
    validation = validate_dataframe_columns(df)
    if not validation["valid"]:
        for col in validation["missing_required"]:
            accumulator.warn(
                message=f"Missing required column: {col}",
                stage=ExtractionStage.SCHEMA_CONVERSION,
            )
    
    # Save outputs
    df.to_csv(output_dir / "extracted_data.csv", index=False)
    df.to_json(output_dir / "extracted_data.json", orient='records', indent=2)
    print(f"  ✓ Saved to {output_dir}/")
    
    # Convert to schema (for validation)
    estimates = convert_dataframe_to_schema(df, metadata)
    print(f"  ✓ Validated {len(estimates)} ExtractedEstimate objects")
    
    # Save error log
    error_log = accumulator.to_dict()
    with open(output_dir / "extraction_log.json", 'w') as f:
        json.dump(error_log, f, indent=2, default=str)
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    elapsed = time.time() - start_time
    print_summary(study_id, df, metadata, accumulator, elapsed, config)
    
    # Clean up
    reset_accumulator()
    
    return metadata, df


def main():
    """CLI entry point with comprehensive argument parsing."""
    parser = argparse.ArgumentParser(
        description='Extract impact evaluation data from papers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli_v2.py --study_id 121058356           # Extract single study (default project)
  python cli_v2.py --all                          # Extract ALL studies in default project
  python cli_v2.py --all --project-id abc123      # Extract all studies in specific project
  python cli_v2.py --study_id 121058356 --fast    # Fast mode (no LLM)
  python cli_v2.py --list                         # List available studies
  python cli_v2.py --list-projects                # List all RAG projects with documents
  python cli_v2.py --study_id 121058356 --no-prose --no-figures  # Tables only

Modes:
  --full     All stages enabled (default)
  --fast     Disable all LLM stages
  --minimal  Just basic table parsing
        """
    )
    
    # Study/Project selection
    selection_group = parser.add_argument_group('Study Selection')
    selection_group.add_argument('--study_id', type=str, default=None,
                        help='Study ID to extract (single study mode)')
    selection_group.add_argument('--all', action='store_true',
                        help='Extract ALL studies in the project')
    selection_group.add_argument('--project-id', type=str, default=DEFAULT_PROJECT_ID,
                        help=f'RAG project UUID (default: {DEFAULT_PROJECT_ID[:8]}...)')
    selection_group.add_argument('--list', action='store_true',
                        help='List available studies in the project and exit')
    selection_group.add_argument('--list-projects', action='store_true',
                        help='List all RAG projects with documents and exit')
    
    # Mode presets
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--full', action='store_true',
                           help='Full extraction mode (default)')
    mode_group.add_argument('--fast', action='store_true',
                           help='Fast mode: disable all LLM stages')
    mode_group.add_argument('--minimal', action='store_true',
                           help='Minimal mode: basic table parsing only')
    
    # Individual stage control
    stage_group = parser.add_argument_group('Stage Control')
    stage_group.add_argument('--no-llm-metadata', action='store_true',
                            help='Disable LLM metadata extraction')
    stage_group.add_argument('--no-llm-classification', action='store_true',
                            help='Disable LLM table classification')
    stage_group.add_argument('--no-enrichment', action='store_true',
                            help='Disable context enrichment')
    stage_group.add_argument('--no-outcome-classification', action='store_true',
                            help='Disable outcome classification')
    stage_group.add_argument('--no-analysis-classification', action='store_true',
                            help='Disable analysis type classification')
    stage_group.add_argument('--no-prose', action='store_true',
                            help='Disable prose extraction fallback')
    stage_group.add_argument('--no-figures', action='store_true',
                            help='Disable figure extraction fallback')
    stage_group.add_argument('--no-effect-sizes', action='store_true',
                            help='Disable effect size calculation')
    
    # Performance
    perf_group = parser.add_argument_group('Performance')
    perf_group.add_argument('--no-cache', action='store_true',
                           help='Disable LLM response caching')
    perf_group.add_argument('--clear-cache', action='store_true',
                           help='Clear LLM cache before running')
    
    # Output
    output_group = parser.add_argument_group('Output')
    output_group.add_argument('--output-dir', type=str,
                             default='extraction_pipeline/outputs',
                             help='Output directory')
    output_group.add_argument('--domain', type=str, default='graduation',
                             help='Domain for outcome classification')
    
    # Debugging
    debug_group = parser.add_argument_group('Debugging')
    debug_group.add_argument('--strict', action='store_true',
                            help='Strict mode: fail on first error')
    debug_group.add_argument('--verbose', '-v', action='store_true',
                            help='Verbose output')
    
    args = parser.parse_args()
    
    # Handle --list-projects
    if args.list_projects:
        print("RAG Projects with processed documents:")
        print("-" * 60)
        projects = list_projects()
        for p in projects:
            print(f"  {p['project_id']}")
            print(f"    Documents: {p['document_count']}")
            print(f"    Path: {p['json_prefix']}")
        if not projects:
            print("  No projects found with processed documents")
        return
    
    # Handle --list
    if args.list:
        print(f"Available studies in project {args.project_id[:8]}...:")
        print("-" * 60)
        studies = list_available_studies(project_id=args.project_id)
        for study_id, filename in studies[:30]:
            print(f"  {study_id:20} | {filename}")
        if len(studies) > 30:
            print(f"  ... and {len(studies) - 30} more")
        print(f"\nTotal: {len(studies)} studies")
        return
    
    # Handle --clear-cache
    if args.clear_cache:
        cache = get_cache()
        count = cache.clear()
        print(f"Cleared {count} cached LLM responses")
    
    # Build configuration
    if args.fast:
        config = PipelineConfig.from_mode(ExtractionMode.FAST)
    elif args.minimal:
        config = PipelineConfig.from_mode(ExtractionMode.MINIMAL)
    else:
        config = PipelineConfig()
    
    # Apply individual overrides
    if args.no_llm_metadata:
        config.use_llm_metadata = False
    if args.no_llm_classification:
        config.use_llm_classification = False
    if args.no_enrichment:
        config.use_context_enrichment = False
    if args.no_outcome_classification:
        config.use_outcome_classification = False
    if args.no_analysis_classification:
        config.use_analysis_classification = False
    if args.no_prose:
        config.use_prose_extraction = False
    if args.no_figures:
        config.use_figure_extraction = False
    if args.no_effect_sizes:
        config.calculate_effect_sizes = False
    if args.no_cache:
        config.use_llm_cache = False
    
    config.output_dir = args.output_dir
    config.domain = args.domain
    config.strict_mode = args.strict
    
    # Configure logging
    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    
    # Determine which studies to run
    if args.all:
        # Extract all studies in the project
        studies = list_available_studies(project_id=args.project_id)
        print(f"{'='*70}")
        print(f"BATCH EXTRACTION: {len(studies)} studies in project {args.project_id[:8]}...")
        print(f"{'='*70}")
        
        results = []
        for i, (study_id, filename) in enumerate(studies, 1):
            print(f"\n[{i}/{len(studies)}] Processing: {study_id}")
            try:
                metadata, df = run_pipeline_v2(study_id, config, project_id=args.project_id)
                results.append({
                    'study_id': study_id,
                    'filename': filename,
                    'rows_extracted': len(df),
                    'status': 'success' if not df.empty else 'no_data',
                })
            except Exception as e:
                logger.error(f"Failed to process {study_id}: {e}")
                results.append({
                    'study_id': study_id,
                    'filename': filename,
                    'rows_extracted': 0,
                    'status': f'error: {str(e)[:50]}',
                })
        
        # Print batch summary
        print(f"\n{'='*70}")
        print("BATCH EXTRACTION COMPLETE")
        print(f"{'='*70}")
        successful = sum(1 for r in results if r['status'] == 'success')
        no_data = sum(1 for r in results if r['status'] == 'no_data')
        errors = sum(1 for r in results if r['status'].startswith('error'))
        total_rows = sum(r['rows_extracted'] for r in results)
        
        print(f"Studies processed: {len(results)}")
        print(f"  Successful:  {successful}")
        print(f"  No data:     {no_data}")
        print(f"  Errors:      {errors}")
        print(f"Total rows extracted: {total_rows}")
        
        # Save batch manifest
        batch_manifest = pd.DataFrame(results)
        manifest_path = Path(config.output_dir) / f"batch_manifest_{args.project_id[:8]}.csv"
        batch_manifest.to_csv(manifest_path, index=False)
        print(f"\nBatch manifest saved to: {manifest_path}")
        
    elif args.study_id:
        # Single study mode
        metadata, df = run_pipeline_v2(args.study_id, config, project_id=args.project_id)
        
        # Print sample output
        if not df.empty:
            print(f"\nSample output:")
            cols = [ColumnNames.TABLE_NUMBER, ColumnNames.TREATMENT_ARM, 
                    ColumnNames.OUTCOME_NAME, ColumnNames.COEFFICIENT, 
                    ColumnNames.STANDARD_ERROR]
            display_cols = [c for c in cols if c in df.columns]
            print(df[display_cols].head(10).to_string())
    else:
        parser.error("Either --study_id or --all is required (or use --list to see available studies)")


if __name__ == "__main__":
    main()
