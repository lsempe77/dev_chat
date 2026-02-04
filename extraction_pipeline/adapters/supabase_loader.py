"""
Supabase Loader Adapter
=======================

Uploads extracted effect estimates to Supabase PostgreSQL.
Enables the chatbot to query quantitative evidence from the database.

Usage:
    # Upload a single study's extractions
    python -m extraction_pipeline.adapters.supabase_loader --study-id 121058356
    
    # Upload all extracted data
    python -m extraction_pipeline.adapters.supabase_loader --all
    
    # Dry run (no database writes)
    python -m extraction_pipeline.adapters.supabase_loader --all --dry-run
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

import pandas as pd
from dotenv import load_dotenv
from loguru import logger
from pydantic import ValidationError

# Load environment variables
load_dotenv()

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.auth.supabase_auth import get_supabase_client
from src.config.settings import settings


# =============================================================================
# Configuration
# =============================================================================

# Version for tracking which extraction pipeline produced the data
EXTRACTION_VERSION = "v2.0-modular"

# Table name in Supabase
ESTIMATES_TABLE = "extracted_estimates"

# Column mapping from CSV to database
CSV_TO_DB_COLUMNS = {
    "study_id": "study_id",
    "table_number": "table_number",
    "table_caption": "table_caption",
    "treatment_arm": "treatment_arm",
    "outcome_name": "outcome_name",
    "outcome_category": "outcome_category",
    "coefficient": "coefficient",
    "standard_error": "standard_error",
    "p_value": "p_value",
    "ci_lower": "ci_lower",
    "ci_upper": "ci_upper",
    "sample_size": "sample_size",
    "n_treatment": "n_treatment",
    "n_control": "n_control",
    "control_mean": "control_mean",
    "control_sd": "control_sd",
    "cohens_d": "cohens_d",
    "hedges_g": "hedges_g",
    "effect_size_assumption": "effect_size_assumption",
    "is_main_effect": "is_main_effect",
    "is_subgroup": "is_subgroup",
    "subgroup_variable": "subgroup_variable",
    "authors": "authors",
    "year": "year",
    "country": "country",
    "study_design": "study_design",
    "page_number": "page_number",
    "pdf_name": "pdf_name",
}


# =============================================================================
# Helper Functions
# =============================================================================

def clean_value(value: Any) -> Any:
    """Clean a value for database insertion."""
    if pd.isna(value):
        return None
    if isinstance(value, float):
        if pd.isna(value) or value != value:  # NaN check
            return None
        # Handle infinity
        if abs(value) == float('inf'):
            return None
    return value


def row_to_db_record(row: pd.Series, rag_project_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Convert a DataFrame row to a database record.
    
    Args:
        row: Pandas Series from extraction DataFrame
        rag_project_id: Optional UUID of RAG project to associate with
        
    Returns:
        Dictionary ready for Supabase insert
    """
    record = {}
    
    for csv_col, db_col in CSV_TO_DB_COLUMNS.items():
        if csv_col in row.index:
            record[db_col] = clean_value(row[csv_col])
    
    # Add metadata fields
    record["extraction_method"] = "pipeline"
    record["extraction_version"] = EXTRACTION_VERSION
    
    # Handle year as integer
    if record.get("year") is not None:
        try:
            record["year"] = int(record["year"])
        except (ValueError, TypeError):
            record["year"] = None
    
    # Handle page_number as integer
    if record.get("page_number") is not None:
        try:
            record["page_number"] = int(record["page_number"])
        except (ValueError, TypeError):
            record["page_number"] = None
    
    # Handle sample sizes as integers
    for col in ["sample_size", "n_treatment", "n_control"]:
        if record.get(col) is not None:
            try:
                record[col] = int(record[col])
            except (ValueError, TypeError):
                record[col] = None
    
    # Handle boolean fields
    if record.get("is_main_effect") is not None:
        record["is_main_effect"] = bool(record["is_main_effect"])
    if record.get("is_subgroup") is not None:
        record["is_subgroup"] = bool(record["is_subgroup"])
    
    # Associate with RAG project if provided
    if rag_project_id:
        record["rag_project_id"] = rag_project_id
    
    return record


def validate_record(record: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate a record before insertion.
    
    Args:
        record: Database record dictionary
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Required fields
    if not record.get("study_id"):
        return False, "Missing study_id"
    if not record.get("treatment_arm"):
        return False, "Missing treatment_arm"
    if not record.get("outcome_name"):
        return False, "Missing outcome_name"
    
    # At least one of coefficient, p_value, or effect size should be present
    has_data = any([
        record.get("coefficient") is not None,
        record.get("p_value") is not None,
        record.get("cohens_d") is not None,
        record.get("hedges_g") is not None,
    ])
    
    if not has_data:
        return False, "No quantitative data (coefficient, p_value, or effect size)"
    
    return True, None


# =============================================================================
# Main Loader Class
# =============================================================================

class SupabaseEstimatesLoader:
    """
    Load extracted estimates to Supabase.
    
    Supports bulk uploads, upsert operations, and dry-run mode.
    """
    
    def __init__(self, dry_run: bool = False):
        """
        Initialize the loader.
        
        Args:
            dry_run: If True, validate but don't write to database
        """
        self.dry_run = dry_run
        self._client = None
    
    @property
    def client(self):
        """Lazy-load Supabase client."""
        if self._client is None:
            self._client = get_supabase_client()
        return self._client
    
    def upload_dataframe(
        self,
        df: pd.DataFrame,
        rag_project_id: Optional[str] = None,
        batch_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Upload a DataFrame of extracted estimates to Supabase.
        
        Args:
            df: DataFrame with extraction results
            rag_project_id: Optional UUID to associate estimates with a RAG project
            batch_size: Number of records to insert per batch
            
        Returns:
            Dictionary with upload statistics
        """
        stats = {
            "total_rows": len(df),
            "valid_rows": 0,
            "invalid_rows": 0,
            "inserted": 0,
            "errors": [],
        }
        
        records = []
        
        # Convert DataFrame to records
        for idx, row in df.iterrows():
            record = row_to_db_record(row, rag_project_id)
            is_valid, error = validate_record(record)
            
            if is_valid:
                records.append(record)
                stats["valid_rows"] += 1
            else:
                stats["invalid_rows"] += 1
                stats["errors"].append({
                    "row": idx,
                    "study_id": record.get("study_id"),
                    "error": error,
                })
        
        logger.info(f"Validated {stats['valid_rows']}/{stats['total_rows']} rows")
        
        if self.dry_run:
            logger.info("DRY RUN - no database writes")
            return stats
        
        # Batch insert
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            try:
                result = self.client.table(ESTIMATES_TABLE).insert(batch).execute()
                stats["inserted"] += len(batch)
                logger.debug(f"Inserted batch {i // batch_size + 1}: {len(batch)} records")
            except Exception as e:
                logger.error(f"Error inserting batch {i // batch_size + 1}: {e}")
                stats["errors"].append({
                    "batch": i // batch_size + 1,
                    "error": str(e),
                })
        
        logger.info(f"Uploaded {stats['inserted']} records to Supabase")
        return stats
    
    def upload_csv(
        self,
        csv_path: Path,
        rag_project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload estimates from a CSV file.
        
        Args:
            csv_path: Path to CSV file
            rag_project_id: Optional UUID to associate estimates with
            
        Returns:
            Upload statistics
        """
        logger.info(f"Loading CSV: {csv_path}")
        df = pd.read_csv(csv_path)
        return self.upload_dataframe(df, rag_project_id)
    
    def upload_study(
        self,
        study_id: str,
        outputs_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Upload a single study's extracted data.
        
        Args:
            study_id: Study identifier
            outputs_dir: Directory containing study outputs (default: extraction_pipeline/outputs)
            
        Returns:
            Upload statistics
        """
        if outputs_dir is None:
            outputs_dir = PROJECT_ROOT / "extraction_pipeline" / "outputs"
        
        study_dir = outputs_dir / study_id
        
        if not study_dir.exists():
            logger.error(f"Study directory not found: {study_dir}")
            return {"error": f"Study directory not found: {study_id}"}
        
        # Look for extracted values CSV
        csv_files = list(study_dir.glob("extracted_values*.csv"))
        if not csv_files:
            logger.error(f"No extracted values CSV found in {study_dir}")
            return {"error": "No extracted values CSV found"}
        
        # Use the most recent one
        csv_path = max(csv_files, key=lambda p: p.stat().st_mtime)
        return self.upload_csv(csv_path)
    
    def delete_study(self, study_id: str) -> Dict[str, Any]:
        """
        Delete all estimates for a study.
        
        Args:
            study_id: Study identifier to delete
            
        Returns:
            Deletion statistics
        """
        if self.dry_run:
            logger.info(f"DRY RUN - would delete estimates for study: {study_id}")
            return {"dry_run": True, "study_id": study_id}
        
        try:
            result = (
                self.client.table(ESTIMATES_TABLE)
                .delete()
                .eq("study_id", study_id)
                .execute()
            )
            count = len(result.data) if result.data else 0
            logger.info(f"Deleted {count} estimates for study: {study_id}")
            return {"deleted": count, "study_id": study_id}
        except Exception as e:
            logger.error(f"Error deleting study {study_id}: {e}")
            return {"error": str(e), "study_id": study_id}
    
    def get_study_count(self, study_id: str) -> int:
        """Get the number of estimates for a study."""
        try:
            result = (
                self.client.table(ESTIMATES_TABLE)
                .select("id", count="exact")
                .eq("study_id", study_id)
                .execute()
            )
            return result.count or 0
        except Exception as e:
            logger.error(f"Error counting estimates for {study_id}: {e}")
            return 0
    
    def get_all_study_ids(self) -> List[str]:
        """Get all unique study IDs in the database."""
        try:
            result = (
                self.client.table(ESTIMATES_TABLE)
                .select("study_id")
                .execute()
            )
            return list(set(r["study_id"] for r in result.data))
        except Exception as e:
            logger.error(f"Error fetching study IDs: {e}")
            return []


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    """CLI entry point for uploading extracted estimates."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Upload extracted estimates to Supabase"
    )
    parser.add_argument(
        "--study-id",
        type=str,
        help="Upload a specific study's extractions",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        help="Upload from a specific CSV file",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Upload all extracted data from full_corpus_for_validation.csv",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without writing to database",
    )
    parser.add_argument(
        "--rag-project-id",
        type=str,
        help="Associate estimates with a RAG project UUID",
    )
    parser.add_argument(
        "--delete",
        type=str,
        metavar="STUDY_ID",
        help="Delete all estimates for a study",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = "DEBUG" if args.verbose else "INFO"
    logger.remove()
    logger.add(sys.stderr, level=log_level)
    
    loader = SupabaseEstimatesLoader(dry_run=args.dry_run)
    
    if args.delete:
        result = loader.delete_study(args.delete)
        print(f"Delete result: {result}")
        return
    
    if args.study_id:
        result = loader.upload_study(args.study_id)
    elif args.csv:
        result = loader.upload_csv(args.csv, args.rag_project_id)
    elif args.all:
        csv_path = PROJECT_ROOT / "extraction_pipeline" / "outputs" / "full_corpus_for_validation.csv"
        if not csv_path.exists():
            logger.error(f"CSV not found: {csv_path}")
            sys.exit(1)
        result = loader.upload_csv(csv_path, args.rag_project_id)
    else:
        parser.print_help()
        sys.exit(1)
    
    # Print summary
    print("\n=== Upload Summary ===")
    print(f"Total rows: {result.get('total_rows', 'N/A')}")
    print(f"Valid rows: {result.get('valid_rows', 'N/A')}")
    print(f"Invalid rows: {result.get('invalid_rows', 'N/A')}")
    print(f"Inserted: {result.get('inserted', 'N/A')}")
    
    if result.get("errors"):
        print(f"\nErrors ({len(result['errors'])}):")
        for err in result["errors"][:10]:  # Show first 10
            print(f"  - {err}")


if __name__ == "__main__":
    main()
