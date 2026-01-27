"""
Extraction module for DevChat.

Topic-agnostic schemas and extractors for systematic review data extraction.
"""

from src.extraction.schemas import (
    ExtractedEstimate,
    CoreNumericFields,
    StudyMetadata,
    OutcomeMetadata,
    InterventionMetadata,
    SourceLocation,
    StandardizedEffectSize,
    DomainSpecificFields,
    ExtractionMode,
    DOMAIN_CONFIGS,
    EXTRACTION_FIELDS,
    get_domain_config,
    list_available_domains,
)

__all__ = [
    "ExtractedEstimate",
    "CoreNumericFields",
    "StudyMetadata",
    "OutcomeMetadata",
    "InterventionMetadata",
    "SourceLocation",
    "StandardizedEffectSize",
    "DomainSpecificFields",
    "ExtractionMode",
    "DOMAIN_CONFIGS",
    "EXTRACTION_FIELDS",
    "get_domain_config",
    "list_available_domains",
]
