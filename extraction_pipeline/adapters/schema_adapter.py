"""
Schema Adapter Module
=====================

Converts pipeline DataFrame output to validated Pydantic ExtractedEstimate objects.
Handles field name mapping and data type normalization.
"""

from typing import Dict, Any, List, Optional
import pandas as pd
from loguru import logger

from src.extraction.schemas import (
    ExtractedEstimate,
    CoreNumericFields,
    StudyMetadata,
    OutcomeMetadata,
    InterventionMetadata,
    SourceLocation,
    StandardizedEffectSize,
    DomainSpecificFields,
)
from extraction_pipeline.core.config import ColumnNames


# =============================================================================
# FIELD MAPPING
# =============================================================================

def normalize_authors(authors: Any) -> Optional[str]:
    """
    Normalize authors field to string format.
    
    Handles:
    - String: "Author1, Author2" → "Author1, Author2"
    - List: ["Author1", "Author2"] → "Author1, Author2"
    - None/NaN: → None
    """
    if authors is None or (isinstance(authors, float) and pd.isna(authors)):
        return None
    
    if isinstance(authors, list):
        return ", ".join(str(a) for a in authors if a)
    
    return str(authors) if authors else None


def safe_int(value: Any) -> Optional[int]:
    """Safely convert to int, returning None for invalid values."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def safe_float(value: Any) -> Optional[float]:
    """Safely convert to float, returning None for invalid values."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def safe_str(value: Any) -> Optional[str]:
    """Safely convert to string, returning None for empty/NaN values."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    return s if s else None


def safe_bool(value: Any) -> Optional[bool]:
    """Safely convert to bool, returning None for invalid values."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', 'yes', '1')
    return bool(value)


# =============================================================================
# ROW TO SCHEMA CONVERSION
# =============================================================================

def row_to_extracted_estimate(
    row: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
) -> ExtractedEstimate:
    """
    Convert a single pipeline result row to ExtractedEstimate Pydantic object.
    
    Handles field name mapping and data type normalization:
    - intervention_name → intervention_type (for schema)
    - authors list → authors string
    - NaN → None
    
    Args:
        row: Single result dict from DataFrame.to_dict('records')
        metadata: Optional study-level metadata dict
        
    Returns:
        Validated ExtractedEstimate object
    """
    meta = metadata or {}
    
    # Build nested objects with proper field mapping
    
    # Study metadata
    study = StudyMetadata(
        study_id=safe_str(row.get(ColumnNames.STUDY_ID, meta.get('study_id'))),
        authors=normalize_authors(row.get(ColumnNames.AUTHORS, meta.get('authors'))),
        year=safe_int(row.get(ColumnNames.YEAR, meta.get('year'))),
        title=safe_str(meta.get('title')),
        country=safe_str(row.get(ColumnNames.COUNTRY, meta.get('country'))),
        study_design=safe_str(row.get(ColumnNames.STUDY_DESIGN, meta.get('study_design'))),
        is_experimental=safe_bool(row.get(ColumnNames.IS_EXPERIMENTAL, meta.get('is_experimental'))),
    )
    
    # Outcome metadata
    outcome = OutcomeMetadata(
        outcome_name=safe_str(row.get(ColumnNames.OUTCOME_NAME)),
        outcome_description=safe_str(row.get(ColumnNames.OUTCOME_DEFINITION)),
        outcome_domain=safe_str(row.get(ColumnNames.OUTCOME_CATEGORY)),
        outcome_unit=safe_str(row.get(ColumnNames.OUTCOME_UNIT)),
    )
    
    # Intervention metadata
    # Note: Map intervention_name to intervention_type for schema compatibility
    intervention = InterventionMetadata(
        intervention_name=safe_str(row.get(ColumnNames.TREATMENT_ARM)),
        intervention_type=safe_str(
            row.get(ColumnNames.INTERVENTION_TYPE) or 
            row.get(ColumnNames.INTERVENTION_NAME) or
            meta.get('intervention_name') or
            meta.get('intervention_type')
        ),
        intervention_description=safe_str(row.get(ColumnNames.INTERVENTION_DESCRIPTION)),
        control_name=safe_str(row.get(ColumnNames.CONTROL_GROUP)),
    )
    
    # Source location
    source = SourceLocation(
        table_number=safe_str(row.get(ColumnNames.TABLE_NUMBER)),
        table_title=safe_str(row.get(ColumnNames.TABLE_CAPTION)),
        page_number=safe_int(row.get(ColumnNames.PAGE_NUMBER)),
        figure_number=safe_str(row.get(ColumnNames.FIGURE_NUMBER)),
        row_identifier=safe_str(row.get(ColumnNames.OUTCOME_NAME)),
        column_identifier=safe_str(row.get(ColumnNames.TREATMENT_ARM)),
    )
    
    # Core numeric fields
    numeric = CoreNumericFields(
        effect_estimate=safe_float(row.get(ColumnNames.COEFFICIENT)),
        standard_error=safe_float(row.get(ColumnNames.STANDARD_ERROR)),
        test_statistic=safe_float(row.get(ColumnNames.T_STATISTIC)),
        p_value=safe_float(row.get(ColumnNames.P_VALUE)),
        p_value_text=safe_str(row.get(ColumnNames.P_VALUE_TEXT)),
        significance_level=safe_str(row.get(ColumnNames.SIGNIFICANCE)),
        ci_lower=safe_float(row.get(ColumnNames.CI_LOWER)),
        ci_upper=safe_float(row.get(ColumnNames.CI_UPPER)),
        n_total=safe_int(row.get(ColumnNames.SAMPLE_SIZE)),
        n_treatment=safe_int(row.get(ColumnNames.N_TREATMENT)),
        n_control=safe_int(row.get(ColumnNames.N_CONTROL)),
        n_clusters=safe_int(row.get(ColumnNames.N_CLUSTERS)),
        follow_up_duration=safe_float(row.get(ColumnNames.FOLLOW_UP_MONTHS, meta.get('follow_up_months'))),
        follow_up_unit="months" if row.get(ColumnNames.FOLLOW_UP_MONTHS) or meta.get('follow_up_months') else None,
    )
    
    # Standardized effect sizes
    standardized = StandardizedEffectSize(
        cohens_d=safe_float(row.get(ColumnNames.COHENS_D)),
        hedges_g=safe_float(row.get(ColumnNames.HEDGES_G)),
        effect_variance=safe_float(row.get(ColumnNames.EFFECT_VARIANCE)),
        effect_se=safe_float(row.get(ColumnNames.EFFECT_SE)),
    )
    
    # Domain-specific fields
    domain_fields = DomainSpecificFields(
        outcome_category=safe_str(row.get(ColumnNames.OUTCOME_CATEGORY)),
        custom_fields={
            "is_main_effect": safe_bool(row.get(ColumnNames.IS_MAIN_EFFECT)),
            "is_subgroup": safe_bool(row.get(ColumnNames.IS_SUBGROUP)),
            "subgroup_variable": safe_str(row.get(ColumnNames.SUBGROUP_VARIABLE)),
            "is_spillover": safe_bool(row.get(ColumnNames.IS_SPILLOVER)),
            "spillover_type": safe_str(row.get(ColumnNames.SPILLOVER_TYPE)),
            "is_cost_outcome": safe_bool(row.get(ColumnNames.IS_COST_OUTCOME)),
            "is_mechanism": safe_bool(row.get(ColumnNames.IS_MECHANISM)),
            "control_mean": safe_float(row.get(ColumnNames.CONTROL_MEAN)),
            "control_sd": safe_float(row.get(ColumnNames.CONTROL_SD)),
            "effect_size_assumption": safe_str(row.get(ColumnNames.EFFECT_SIZE_ASSUMPTION)),
        }
    )
    
    # Clean up custom_fields - remove None values
    domain_fields.custom_fields = {
        k: v for k, v in domain_fields.custom_fields.items() if v is not None
    }
    
    # Extraction metadata
    extraction_confidence = safe_float(row.get(ColumnNames.EXTRACTION_CONFIDENCE))
    extraction_method = safe_str(row.get(ColumnNames.EXTRACTION_SOURCE, "table_parse"))
    
    return ExtractedEstimate(
        numeric=numeric,
        study=study,
        outcome=outcome,
        intervention=intervention,
        source=source,
        standardized=standardized,
        domain_fields=domain_fields,
        extraction_confidence=extraction_confidence,
        extraction_method=extraction_method,
    )


def convert_dataframe_to_schema(
    df: pd.DataFrame,
    metadata: Optional[Dict[str, Any]] = None,
    validate: bool = True,
) -> List[ExtractedEstimate]:
    """
    Convert entire DataFrame to list of ExtractedEstimate objects.
    
    Args:
        df: DataFrame with extraction results
        metadata: Optional study-level metadata
        validate: If True, log validation warnings
        
    Returns:
        List of validated ExtractedEstimate objects
    """
    if df.empty:
        return []
    
    estimates = []
    errors = []
    
    for idx, row in df.iterrows():
        try:
            estimate = row_to_extracted_estimate(row.to_dict(), metadata)
            estimates.append(estimate)
        except Exception as e:
            errors.append((idx, str(e)))
            logger.warning(f"Failed to convert row {idx}: {e}")
    
    if errors and validate:
        logger.warning(f"Schema conversion: {len(errors)} rows failed validation")
    
    logger.info(f"Converted {len(estimates)} rows to ExtractedEstimate schema")
    return estimates


def validate_dataframe_columns(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Validate DataFrame columns against expected schema.
    
    Returns dict with:
    - missing_required: List of missing required columns
    - extra_columns: List of columns not in schema
    - type_issues: Dict of columns with unexpected types
    """
    from extraction_pipeline.core.config import REQUIRED_COLUMNS, NUMERIC_COLUMNS
    
    result = {
        "missing_required": [],
        "extra_columns": [],
        "type_issues": {},
        "valid": True,
    }
    
    # Check required columns
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            result["missing_required"].append(col)
            result["valid"] = False
    
    # Check numeric columns have appropriate types
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            if not pd.api.types.is_numeric_dtype(df[col]) and df[col].notna().any():
                # Check if values are convertible
                try:
                    pd.to_numeric(df[col], errors='raise')
                except:
                    result["type_issues"][col] = f"Expected numeric, got {df[col].dtype}"
    
    return result


def estimates_to_dataframe(estimates: List[ExtractedEstimate]) -> pd.DataFrame:
    """
    Convert list of ExtractedEstimate objects back to flat DataFrame.
    
    Useful for:
    - Exporting validated data
    - Integration with analysis tools expecting flat format
    """
    if not estimates:
        return pd.DataFrame()
    
    rows = []
    for est in estimates:
        row = {
            # Study
            ColumnNames.STUDY_ID: est.study.study_id,
            ColumnNames.AUTHORS: est.study.authors,
            ColumnNames.YEAR: est.study.year,
            ColumnNames.TITLE: est.study.title,
            ColumnNames.COUNTRY: est.study.country,
            ColumnNames.STUDY_DESIGN: est.study.study_design,
            ColumnNames.IS_EXPERIMENTAL: est.study.is_experimental,
            
            # Source
            ColumnNames.TABLE_NUMBER: est.source.table_number,
            ColumnNames.TABLE_CAPTION: est.source.table_title,
            ColumnNames.PAGE_NUMBER: est.source.page_number,
            
            # Outcome
            ColumnNames.OUTCOME_NAME: est.outcome.outcome_name,
            ColumnNames.OUTCOME_DEFINITION: est.outcome.outcome_description,
            ColumnNames.OUTCOME_CATEGORY: est.outcome.outcome_domain,
            ColumnNames.OUTCOME_UNIT: est.outcome.outcome_unit,
            
            # Intervention
            ColumnNames.TREATMENT_ARM: est.intervention.intervention_name,
            ColumnNames.INTERVENTION_TYPE: est.intervention.intervention_type,
            ColumnNames.CONTROL_GROUP: est.intervention.control_name,
            
            # Numerics
            ColumnNames.COEFFICIENT: est.numeric.effect_estimate,
            ColumnNames.STANDARD_ERROR: est.numeric.standard_error,
            ColumnNames.T_STATISTIC: est.numeric.test_statistic,
            ColumnNames.P_VALUE: est.numeric.p_value,
            ColumnNames.P_VALUE_TEXT: est.numeric.p_value_text,
            ColumnNames.SIGNIFICANCE: est.numeric.significance_level,
            ColumnNames.CI_LOWER: est.numeric.ci_lower,
            ColumnNames.CI_UPPER: est.numeric.ci_upper,
            ColumnNames.SAMPLE_SIZE: est.numeric.n_total,
            ColumnNames.N_TREATMENT: est.numeric.n_treatment,
            ColumnNames.N_CONTROL: est.numeric.n_control,
            ColumnNames.N_CLUSTERS: est.numeric.n_clusters,
            ColumnNames.FOLLOW_UP_MONTHS: est.numeric.follow_up_duration,
            
            # Standardized
            ColumnNames.COHENS_D: est.standardized.cohens_d,
            ColumnNames.HEDGES_G: est.standardized.hedges_g,
            ColumnNames.EFFECT_VARIANCE: est.standardized.effect_variance,
            ColumnNames.EFFECT_SE: est.standardized.effect_se,
            
            # Extraction metadata
            ColumnNames.EXTRACTION_CONFIDENCE: est.extraction_confidence,
            ColumnNames.EXTRACTION_SOURCE: est.extraction_method,
        }
        
        # Add domain custom fields
        if est.domain_fields.custom_fields:
            for key, value in est.domain_fields.custom_fields.items():
                row[key] = value
        
        rows.append(row)
    
    return pd.DataFrame(rows)
