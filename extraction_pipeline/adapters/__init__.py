"""
Adapters Module
===============

Schema conversion and data format adapters.
"""

from .schema_adapter import (
    row_to_extracted_estimate,
    convert_dataframe_to_schema,
    validate_dataframe_columns,
    estimates_to_dataframe,
    normalize_authors,
)

# Supabase loader for production integration
try:
    from .supabase_loader import SupabaseEstimatesLoader
except ImportError:
    SupabaseEstimatesLoader = None  # Optional dependency

__all__ = [
    "row_to_extracted_estimate",
    "convert_dataframe_to_schema",
    "validate_dataframe_columns",
    "estimates_to_dataframe",
    "normalize_authors",
    "SupabaseEstimatesLoader",
]
