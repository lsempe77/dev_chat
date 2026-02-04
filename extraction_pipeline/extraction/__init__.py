"""
Extraction Module
=================

Extract data from tables, prose, and figures.
"""

from .extractors import (
    detect_table_orientation,
    extract_treatments_in_cols_table,
    extract_outcomes_in_rows_se_split,
    extract_comparison_format_table,
    extract_transposed_table,
    extract_results_table,
)
from .metadata import extract_metadata, extract_metadata_llm
from .sample_sizes import extract_sample_sizes_from_table, extract_sample_sizes_from_prose
from .prose import extract_effects_from_prose, extract_effects_from_figures

__all__ = [
    # Table extractors
    'detect_table_orientation',
    'extract_treatments_in_cols_table',
    'extract_outcomes_in_rows_se_split',
    'extract_comparison_format_table',
    'extract_transposed_table',
    'extract_results_table',
    # Metadata
    'extract_metadata',
    'extract_metadata_llm',
    # Sample sizes
    'extract_sample_sizes_from_table',
    'extract_sample_sizes_from_prose',
    # Prose/figures
    'extract_effects_from_prose',
    'extract_effects_from_figures',
]
