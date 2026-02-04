"""
Enrichment Module
=================

Post-extraction enrichment: effect sizes, outcome classification, context.
"""

# Import from postprocessing to avoid duplication
from ..postprocessing.effect_sizes import calculate_effect_sizes
from .outcomes import classify_outcomes
from .analysis_type import classify_analysis_type
from .context import enrich_with_context

__all__ = [
    'calculate_effect_sizes',
    'classify_outcomes',
    'classify_analysis_type',
    'enrich_with_context',
]
