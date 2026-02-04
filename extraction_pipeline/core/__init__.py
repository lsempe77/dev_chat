"""
Extraction Pipeline Core Module
===============================

Core infrastructure components for the extraction pipeline:
- Error handling and observability
- LLM client with caching
- R2 storage client
- Configuration management
"""

from .errors import (
    ExtractionError, 
    ExtractionWarning, 
    ErrorAccumulator,
    ExtractionStage
)
from .llm_client import (
    LLMClient, 
    LLMResponse, 
    call_llm,
    sanitize_llm_response,
    parse_llm_json,
    get_cached_llm_response,
)
from .storage import get_r2_client, load_mineru_json
from .config import PipelineConfig, DEFAULT_CONFIG

__all__ = [
    # Errors
    "ExtractionError",
    "ExtractionWarning", 
    "ErrorAccumulator",
    "ExtractionStage",
    # LLM
    "LLMClient",
    "LLMResponse",
    "call_llm",
    "sanitize_llm_response",
    "parse_llm_json",
    "get_cached_llm_response",
    # Storage
    "get_r2_client",
    "load_mineru_json",
    # Config
    "PipelineConfig",
    "DEFAULT_CONFIG",
]
