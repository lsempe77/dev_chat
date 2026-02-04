"""
Postprocessing Module
=====================

Post-extraction processing including:
- MinerU output cleanup
- List of Tables parsing
- Effect size calculations
"""

from .effect_sizes import (
    calculate_effect_sizes,
    calculate_effect_sizes_for_row,
    calculate_cohens_d,
    calculate_hedges_g,
    calculate_effect_variance,
    summarize_effect_sizes,
    EffectSizeAssumption,
)
from .mineru import MinerUPostProcessor
from .lot_parser import parse_list_of_tables, match_tables_to_list, repair_table_captions

__all__ = [
    "calculate_effect_sizes",
    "calculate_effect_sizes_for_row",
    "calculate_cohens_d",
    "calculate_hedges_g",
    "calculate_effect_variance",
    "summarize_effect_sizes",
    "EffectSizeAssumption",
]
