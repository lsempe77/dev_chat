"""
Table Extractors
================

Different extractors for various table formats.
"""

from .base import detect_table_orientation
from .treatments_cols import extract_treatments_in_cols_table
from .outcomes_rows import extract_outcomes_in_rows_se_split
from .comparison import extract_comparison_format_table
from .transposed import extract_transposed_table
from .standard import extract_results_table

__all__ = [
    'detect_table_orientation',
    'extract_treatments_in_cols_table',
    'extract_outcomes_in_rows_se_split',
    'extract_comparison_format_table',
    'extract_transposed_table',
    'extract_results_table',
]
