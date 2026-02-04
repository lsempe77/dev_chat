"""
Combine individual study extraction outputs into unified files for validation app.

Creates:
- full_corpus_all_studies.csv - All extracted data
- full_corpus_for_validation.csv - Subset with key columns for validation UI
"""

import os
import sys
from pathlib import Path
import pandas as pd
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = Path(__file__).parent
OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUT_ALL = OUTPUTS_DIR / "full_corpus_all_studies.csv"
OUTPUT_VALIDATION = OUTPUTS_DIR / "full_corpus_for_validation.csv"


def find_study_outputs(outputs_dir: Path) -> tuple[list[Path], list[str]]:
    """Find all study directories, return both those with data and empty ones."""
    csv_files = []
    empty_studies = []
    
    for study_dir in outputs_dir.iterdir():
        if study_dir.is_dir():
            csv_path = study_dir / "extracted_data.csv"
            if csv_path.exists():
                csv_files.append(csv_path)
            else:
                # Check if it has metadata.json (means extraction ran but found nothing)
                metadata_path = study_dir / "metadata.json"
                if metadata_path.exists():
                    empty_studies.append(study_dir.name)
    
    return csv_files, empty_studies


def combine_study_outputs(csv_files: list[Path], empty_studies: list[str]) -> pd.DataFrame:
    """Combine all study CSVs into one DataFrame, including empty studies."""
    dfs = []
    for csv_path in csv_files:
        try:
            df = pd.read_csv(csv_path)
            # Add study_id from directory name if not present
            study_id = csv_path.parent.name
            if 'study_id' not in df.columns:
                df['study_id'] = study_id
            dfs.append(df)
            logger.info(f"Loaded {len(df)} rows from {study_id}")
        except Exception as e:
            logger.error(f"Failed to load {csv_path}: {e}")
    
    # Add empty studies with a single row (for tracking)
    for study_id in empty_studies:
        empty_row = pd.DataFrame([{
            'study_id': study_id,
            'table_number': None,
            'outcome_name': '[NO DATA EXTRACTED]',
            'coefficient': None,
            'standard_error': None,
            'rows_extracted': 0,
        }])
        dfs.append(empty_row)
        logger.info(f"Added empty study marker for {study_id}")
    
    if not dfs:
        return pd.DataFrame()
    
    combined = pd.concat(dfs, ignore_index=True)
    logger.info(f"Combined {len(combined)} total rows from {len(csv_files)} studies + {len(empty_studies)} empty studies")
    return combined


def create_validation_subset(df: pd.DataFrame) -> pd.DataFrame:
    """Create validation subset with key columns for the UI."""
    # Key columns for validation app
    validation_columns = [
        'study_id',
        'table_number',
        'table_caption',
        'treatment_arm',
        'outcome_name',
        'outcome_category',
        'coefficient',
        'standard_error',
        'p_value',
        'ci_lower',
        'ci_upper',
        'sample_size',
        'n_treatment',
        'n_control',
        'control_mean',
        'control_sd',
        'cohens_d',
        'hedges_g',
        'effect_size_assumption',
        'is_main_effect',
        'is_subgroup',
        'subgroup_variable',
        'authors',
        'year',
        'country',
        'study_design',
        'page_number',
        'pdf_name',
    ]
    
    # Add pdf_name from study_id if not present
    if 'pdf_name' not in df.columns:
        df['pdf_name'] = df['study_id'].apply(lambda x: f"PDFs_of_included_programs_{x}.pdf")
    
    # Select only columns that exist
    available_columns = [c for c in validation_columns if c in df.columns]
    missing_columns = [c for c in validation_columns if c not in df.columns]
    
    if missing_columns:
        logger.warning(f"Missing columns: {missing_columns}")
    
    return df[available_columns].copy()


def main():
    """Main entry point."""
    logger.info("Combining extraction outputs...")
    
    # Find all study outputs (including empty ones)
    csv_files, empty_studies = find_study_outputs(OUTPUTS_DIR)
    logger.info(f"Found {len(csv_files)} studies with data, {len(empty_studies)} empty studies")
    
    if not csv_files and not empty_studies:
        logger.error("No extraction outputs found. Run batch extraction first.")
        return
    
    # Combine all outputs
    combined_df = combine_study_outputs(csv_files, empty_studies)
    
    if combined_df.empty:
        logger.error("No data to combine")
        return
    
    # Save full corpus
    combined_df.to_csv(OUTPUT_ALL, index=False)
    logger.info(f"Saved full corpus: {OUTPUT_ALL} ({len(combined_df)} rows)")
    
    # Create and save validation subset
    validation_df = create_validation_subset(combined_df)
    validation_df.to_csv(OUTPUT_VALIDATION, index=False)
    logger.info(f"Saved validation file: {OUTPUT_VALIDATION} ({len(validation_df)} rows)")
    
    # Export to Excel for easier review
    excel_path = OUTPUTS_DIR / "full_corpus_for_validation.xlsx"
    try:
        validation_df.to_excel(excel_path, index=False, engine='openpyxl')
        logger.info(f"Saved Excel file: {excel_path}")
    except ImportError:
        logger.warning("openpyxl not installed, skipping Excel export. Run: pip install openpyxl")
    except Exception as e:
        logger.warning(f"Excel export failed: {e}")
    
    # Summary stats
    print("\n" + "=" * 60)
    print("COMBINATION COMPLETE")
    print("=" * 60)
    print(f"Studies with data: {len(csv_files)}")
    print(f"Studies without data: {len(empty_studies)}")
    print(f"Total studies: {combined_df['study_id'].nunique()}")
    print(f"Total rows: {len(combined_df)}")
    print(f"Unique outcomes: {combined_df['outcome_name'].nunique() if 'outcome_name' in combined_df.columns else 'N/A'}")
    
    if empty_studies:
        print(f"\nEmpty studies (no extractable data):")
        for s in empty_studies:
            print(f"  - {s}")
    
    print(f"\nFiles created:")
    print(f"  - {OUTPUT_ALL}")
    print(f"  - {OUTPUT_VALIDATION}")
    print(f"  - {excel_path}")


if __name__ == "__main__":
    main()
