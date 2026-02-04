"""
Pipeline Configuration
======================

Centralized configuration for the extraction pipeline.
Supports CLI flags and environment variables.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


class ExtractionMode(str, Enum):
    """Extraction mode controls which stages run."""
    FULL = "full"           # All stages, all LLM features
    FAST = "fast"           # Skip expensive LLM stages
    TABLES_ONLY = "tables"  # Only table extraction, no prose/figures
    MINIMAL = "minimal"     # Just metadata + basic table parsing


@dataclass
class PipelineConfig:
    """
    Configuration for extraction pipeline.
    
    All boolean flags default to True for full extraction.
    Disable stages for faster/cheaper runs.
    
    Usage:
        config = PipelineConfig(
            use_llm_classification=False,
            use_prose_extraction=False,
        )
        df = run_pipeline(study_id, config=config)
    """
    
    # === Stage Control ===
    
    # Metadata extraction
    use_llm_metadata: bool = True  # Use LLM to extract author/country/design
    
    # Table classification
    use_llm_classification: bool = True  # Use LLM for ambiguous tables
    
    # Context enrichment
    use_context_enrichment: bool = True  # LLM for outcome definitions
    use_outcome_classification: bool = True  # LLM for outcome categories
    use_analysis_classification: bool = True  # LLM for subgroup/spillover detection
    
    # Fallback extraction
    use_prose_extraction: bool = True  # Try prose when no tables
    use_figure_extraction: bool = True  # Try figures when no prose
    use_sample_size_prose: bool = True  # Extract sample sizes from prose
    
    # Effect size calculation
    calculate_effect_sizes: bool = True
    
    # === Performance ===
    
    # Caching
    use_llm_cache: bool = True  # Cache LLM responses
    cache_dir: Optional[str] = None  # Cache directory (None = default)
    
    # Parallelization (future)
    max_concurrent_tables: int = 1  # Tables to process in parallel
    
    # === Domain ===
    
    domain: str = "graduation"  # Domain for outcome categories
    
    # === Output ===
    
    output_dir: str = "extraction_pipeline/outputs"
    save_intermediate: bool = False  # Save intermediate results
    
    # === Error Handling ===
    
    strict_mode: bool = False  # Raise on first error
    
    # === LLM Settings ===
    
    llm_model: str = "anthropic/claude-3.5-haiku"
    llm_max_tokens_classification: int = 100
    llm_max_tokens_extraction: int = 2000
    llm_temperature: float = 0.0
    
    @classmethod
    def from_mode(cls, mode: ExtractionMode) -> "PipelineConfig":
        """Create config from extraction mode preset."""
        if mode == ExtractionMode.FULL:
            return cls()
        
        elif mode == ExtractionMode.FAST:
            return cls(
                use_llm_metadata=False,
                use_llm_classification=False,
                use_context_enrichment=False,
                use_outcome_classification=False,
                use_analysis_classification=False,
                use_prose_extraction=False,
                use_figure_extraction=False,
            )
        
        elif mode == ExtractionMode.TABLES_ONLY:
            return cls(
                use_prose_extraction=False,
                use_figure_extraction=False,
            )
        
        elif mode == ExtractionMode.MINIMAL:
            return cls(
                use_llm_metadata=False,
                use_llm_classification=False,
                use_context_enrichment=False,
                use_outcome_classification=False,
                use_analysis_classification=False,
                use_prose_extraction=False,
                use_figure_extraction=False,
                use_sample_size_prose=False,
                calculate_effect_sizes=False,
            )
        
        return cls()
    
    @property
    def is_llm_enabled(self) -> bool:
        """Check if any LLM feature is enabled."""
        return any([
            self.use_llm_metadata,
            self.use_llm_classification,
            self.use_context_enrichment,
            self.use_outcome_classification,
            self.use_analysis_classification,
            self.use_prose_extraction,
            self.use_figure_extraction,
        ])
    
    def summary(self) -> str:
        """Generate human-readable config summary."""
        llm_stages = []
        if self.use_llm_metadata:
            llm_stages.append("metadata")
        if self.use_llm_classification:
            llm_stages.append("classification")
        if self.use_context_enrichment:
            llm_stages.append("enrichment")
        if self.use_outcome_classification:
            llm_stages.append("outcomes")
        if self.use_analysis_classification:
            llm_stages.append("analysis")
        if self.use_prose_extraction:
            llm_stages.append("prose")
        if self.use_figure_extraction:
            llm_stages.append("figures")
        
        return (
            f"Config: domain={self.domain}, "
            f"LLM stages=[{', '.join(llm_stages) or 'none'}], "
            f"cache={self.use_llm_cache}, "
            f"strict={self.strict_mode}"
        )


# Default configuration
DEFAULT_CONFIG = PipelineConfig()


# =============================================================================
# COLUMN SCHEMA CONSTANTS
# =============================================================================

# Canonical column names to ensure consistency between extraction functions,
# DataFrame columns, and Pydantic schema

class ColumnNames:
    """
    Canonical column names used throughout the pipeline.
    
    Using these constants ensures consistency and catches typos at import time.
    """
    
    # Identifiers
    STUDY_ID = "study_id"
    ESTIMATE_ID = "estimate_id"
    
    # Study metadata
    TITLE = "title"
    AUTHORS = "authors"
    YEAR = "year"
    COUNTRY = "country"
    STUDY_DESIGN = "study_design"
    IS_EXPERIMENTAL = "is_experimental"
    FOLLOW_UP_MONTHS = "follow_up_months"
    
    # Source location
    TABLE_NUMBER = "table_number"
    TABLE_CAPTION = "table_caption"
    PAGE_NUMBER = "page_number"
    SECTION = "section"
    FIGURE_NUMBER = "figure_number"
    
    # Outcome
    OUTCOME_NAME = "outcome_name"
    OUTCOME_DEFINITION = "outcome_definition"
    OUTCOME_CATEGORY = "outcome_category"
    OUTCOME_UNIT = "outcome_unit"
    OUTCOME_TIMEPOINT = "outcome_timepoint"
    
    # Intervention
    TREATMENT_ARM = "treatment_arm"
    CONTROL_GROUP = "control_group"
    INTERVENTION_NAME = "intervention_name"  # Study-level
    INTERVENTION_TYPE = "intervention_type"  # For schema mapping
    INTERVENTION_DESCRIPTION = "intervention_description"
    
    # Core numerics
    COEFFICIENT = "coefficient"
    STANDARD_ERROR = "standard_error"
    T_STATISTIC = "t_statistic"
    P_VALUE = "p_value"
    P_VALUE_TEXT = "p_value_text"
    SIGNIFICANCE = "significance"
    CI_LOWER = "ci_lower"
    CI_UPPER = "ci_upper"
    
    # Sample sizes
    SAMPLE_SIZE = "sample_size"
    N_TREATMENT = "n_treatment"
    N_CONTROL = "n_control"
    N_CLUSTERS = "n_clusters"
    
    # Control group stats
    CONTROL_MEAN = "control_mean"
    CONTROL_SD = "control_sd"
    
    # Calculated effect sizes
    COHENS_D = "cohens_d"
    HEDGES_G = "hedges_g"
    EFFECT_VARIANCE = "effect_variance"
    EFFECT_SE = "effect_se"
    
    # Analysis type classification
    IS_MAIN_EFFECT = "is_main_effect"
    IS_SUBGROUP = "is_subgroup"
    SUBGROUP_VARIABLE = "subgroup_variable"
    IS_SPILLOVER = "is_spillover"
    SPILLOVER_TYPE = "spillover_type"
    IS_COST_OUTCOME = "is_cost_outcome"
    IS_MECHANISM = "is_mechanism"
    
    # Extraction metadata
    EXTRACTION_SOURCE = "extraction_source"
    EXTRACTION_CONFIDENCE = "extraction_confidence"
    LITERAL_CELL_TEXT = "literal_cell_text"
    TABLE_ORIENTATION = "table_orientation"
    
    # Effect size assumptions (new)
    EFFECT_SIZE_ASSUMPTION = "effect_size_assumption"


# Lists for validation
REQUIRED_COLUMNS = [
    ColumnNames.STUDY_ID,
    ColumnNames.OUTCOME_NAME,
    ColumnNames.TREATMENT_ARM,
    ColumnNames.COEFFICIENT,
]

NUMERIC_COLUMNS = [
    ColumnNames.COEFFICIENT,
    ColumnNames.STANDARD_ERROR,
    ColumnNames.P_VALUE,
    ColumnNames.CI_LOWER,
    ColumnNames.CI_UPPER,
    ColumnNames.SAMPLE_SIZE,
    ColumnNames.N_TREATMENT,
    ColumnNames.N_CONTROL,
    ColumnNames.CONTROL_MEAN,
    ColumnNames.CONTROL_SD,
    ColumnNames.COHENS_D,
    ColumnNames.HEDGES_G,
]
