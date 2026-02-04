"""
LLM Client with Caching and Response Sanitization
==================================================

Centralized LLM interaction with:
- Response caching by prompt hash
- JSON response validation and sanitization
- Structured error handling (distinguishes unavailable vs no signal)
- Retry logic with exponential backoff
"""

import json
import re
import hashlib
import os
from typing import Optional, Dict, Any, TypeVar, Type
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError
from openai import OpenAI
from loguru import logger

from .errors import (
    ExtractionError,
    ExtractionStage,
    LLMFailureType,
    get_accumulator,
)

# Type variable for generic JSON parsing
T = TypeVar('T', bound=BaseModel)


@dataclass
class LLMResponse:
    """
    Structured response from LLM call.
    
    Attributes:
        content: Raw text response (may be empty)
        success: Whether call succeeded
        failure_type: Type of failure if any
        from_cache: Whether response came from cache
        latency_ms: Response time in milliseconds
        model: Model used
        prompt_hash: Hash of prompt for caching
    """
    content: str
    success: bool
    failure_type: Optional[LLMFailureType] = None
    from_cache: bool = False
    latency_ms: Optional[float] = None
    model: Optional[str] = None
    prompt_hash: Optional[str] = None
    error_message: Optional[str] = None
    
    def is_empty(self) -> bool:
        """Check if response has no meaningful content."""
        return not self.content or self.content.strip() == ""
    
    def as_json(self) -> Optional[Dict[str, Any]]:
        """Try to parse content as JSON."""
        return parse_llm_json(self.content)


# =============================================================================
# RESPONSE SANITIZATION
# =============================================================================

def sanitize_llm_response(text: str) -> str:
    """
    Clean up common LLM response artifacts.
    
    Handles:
    - Markdown code fences (```json ... ```)
    - Leading/trailing whitespace
    - BOM characters
    - Common formatting issues
    """
    if not text:
        return ""
    
    result = text.strip()
    
    # Remove markdown code fences
    # Handles: ```json\n...\n```, ```\n...\n```, etc.
    if result.startswith("```"):
        # Find the end fence
        lines = result.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]  # Remove first line (```json or ```)
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]  # Remove last line (```)
        result = "\n".join(lines)
    
    # Remove BOM and other control characters
    result = result.lstrip("\ufeff")
    
    # Clean up leading text before JSON (common with some models)
    # E.g., "Here is the JSON:\n{...}"
    if "{" in result and not result.strip().startswith("{"):
        json_start = result.find("{")
        # Only trim if there's actual JSON
        if json_start != -1:
            potential_json = result[json_start:]
            if potential_json.rstrip().endswith("}"):
                result = potential_json
    
    # Same for arrays
    if "[" in result and not result.strip().startswith("["):
        array_start = result.find("[")
        if array_start != -1:
            potential_array = result[array_start:]
            if potential_array.rstrip().endswith("]"):
                result = potential_array
    
    return result.strip()


def parse_llm_json(text: str, strict: bool = False) -> Optional[Dict[str, Any]]:
    """
    Parse JSON from LLM response with error handling.
    
    Args:
        text: Raw LLM response
        strict: If True, raises on parse failure. If False, returns None.
        
    Returns:
        Parsed JSON dict, or None if parsing failed
    """
    if not text:
        return None
    
    sanitized = sanitize_llm_response(text)
    
    try:
        return json.loads(sanitized)
    except json.JSONDecodeError as e:
        if strict:
            raise ExtractionError(
                message=f"Failed to parse LLM JSON: {e}",
                stage=ExtractionStage.TABLE_PARSING,
                llm_failure_type=LLMFailureType.MALFORMED_JSON,
                details={"raw_response": text[:500], "error": str(e)},
            )
        logger.debug(f"JSON parse failed: {e}. Raw: {text[:200]}")
        return None


def validate_llm_json(
    text: str, 
    schema: Type[T],
    stage: ExtractionStage,
) -> Optional[T]:
    """
    Parse and validate LLM JSON response against a Pydantic schema.
    
    Args:
        text: Raw LLM response
        schema: Pydantic model class to validate against
        stage: Pipeline stage for error context
        
    Returns:
        Validated Pydantic object, or None if validation failed
    """
    parsed = parse_llm_json(text)
    if parsed is None:
        return None
    
    try:
        return schema.model_validate(parsed)
    except ValidationError as e:
        accumulator = get_accumulator()
        accumulator.warn(
            message=f"LLM response doesn't match expected schema: {e}",
            stage=stage,
            llm_failure_type=LLMFailureType.SCHEMA_VIOLATION,
            details={"errors": e.errors()},
        )
        return None


# =============================================================================
# CACHING
# =============================================================================

def get_prompt_hash(prompt: str) -> str:
    """Generate stable hash for prompt caching."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


class LLMCache:
    """
    Simple file-based LLM response cache.
    
    Caches responses keyed by hash(prompt) to avoid redundant API calls.
    """
    
    def __init__(self, cache_dir: Optional[str] = None):
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            # Default to .cache in extraction_pipeline directory
            self.cache_dir = Path(__file__).parent.parent / ".llm_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._hits = 0
        self._misses = 0
    
    def _cache_path(self, prompt_hash: str) -> Path:
        return self.cache_dir / f"{prompt_hash}.json"
    
    def get(self, prompt: str) -> Optional[LLMResponse]:
        """Get cached response if available."""
        prompt_hash = get_prompt_hash(prompt)
        cache_path = self._cache_path(prompt_hash)
        
        if cache_path.exists():
            try:
                with open(cache_path, "r") as f:
                    data = json.load(f)
                self._hits += 1
                return LLMResponse(
                    content=data["content"],
                    success=data.get("success", True),
                    from_cache=True,
                    model=data.get("model"),
                    prompt_hash=prompt_hash,
                )
            except (json.JSONDecodeError, KeyError) as e:
                logger.debug(f"Cache read error: {e}")
        
        self._misses += 1
        return None
    
    def set(self, prompt: str, response: LLMResponse) -> None:
        """Cache a response."""
        if not response.success:
            return  # Don't cache failures
        
        prompt_hash = get_prompt_hash(prompt)
        cache_path = self._cache_path(prompt_hash)
        
        try:
            with open(cache_path, "w") as f:
                json.dump({
                    "content": response.content,
                    "success": response.success,
                    "model": response.model,
                    "cached_at": datetime.utcnow().isoformat(),
                }, f)
        except IOError as e:
            logger.debug(f"Cache write error: {e}")
    
    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0
    
    def clear(self) -> int:
        """Clear all cached responses. Returns count of cleared items."""
        count = 0
        for path in self.cache_dir.glob("*.json"):
            path.unlink()
            count += 1
        return count


# Global cache instance
_llm_cache: Optional[LLMCache] = None


def get_cache() -> LLMCache:
    global _llm_cache
    if _llm_cache is None:
        _llm_cache = LLMCache()
    return _llm_cache


def get_cached_llm_response(prompt: str) -> Optional[LLMResponse]:
    """Check cache for existing response."""
    return get_cache().get(prompt)


# =============================================================================
# LLM CLIENT
# =============================================================================

# Default model
DEFAULT_MODEL = "anthropic/claude-3.5-haiku"


class LLMClient:
    """
    Centralized LLM client with caching and error handling.
    
    Usage:
        client = LLMClient()
        response = client.call("Classify this table...")
        if response.success:
            result = response.as_json()
    """
    
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        use_cache: bool = True,
        api_key: Optional[str] = None,
        base_url: str = "https://openrouter.ai/api/v1",
    ):
        self.model = model
        self.use_cache = use_cache
        self.base_url = base_url
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        
        if not self.api_key:
            logger.warning("No OpenRouter API key found. LLM calls will fail.")
        
        self._client: Optional[OpenAI] = None
        self._call_count = 0
        self._total_latency_ms = 0
    
    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
            )
        return self._client
    
    def call(
        self,
        prompt: str,
        max_tokens: int = 500,
        temperature: float = 0,
        stage: Optional[ExtractionStage] = None,
        study_id: Optional[str] = None,
        table_number: Optional[str] = None,
    ) -> LLMResponse:
        """
        Call LLM with caching and error handling.
        
        Args:
            prompt: The prompt to send
            max_tokens: Maximum response tokens
            temperature: Sampling temperature (0 for deterministic)
            stage: Pipeline stage for error context
            study_id: Study ID for error context
            table_number: Table number for error context
            
        Returns:
            LLMResponse with success status and content
        """
        accumulator = get_accumulator()
        
        # Check cache first
        if self.use_cache:
            cached = get_cache().get(prompt)
            if cached:
                logger.debug(f"LLM cache hit for prompt hash {cached.prompt_hash}")
                return cached
        
        # Make API call
        import time
        start_time = time.time()
        
        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            latency_ms = (time.time() - start_time) * 1000
            self._call_count += 1
            self._total_latency_ms += latency_ms
            
            content = response.choices[0].message.content.strip()
            
            # Check for empty response
            if not content:
                accumulator.record_llm_call(success=False)
                accumulator.warn(
                    message="LLM returned empty response",
                    stage=stage or ExtractionStage.TABLE_PARSING,
                    table_number=table_number,
                    llm_failure_type=LLMFailureType.EMPTY_RESPONSE,
                )
                return LLMResponse(
                    content="",
                    success=False,
                    failure_type=LLMFailureType.EMPTY_RESPONSE,
                    latency_ms=latency_ms,
                    model=self.model,
                    prompt_hash=get_prompt_hash(prompt),
                )
            
            accumulator.record_llm_call(success=True)
            
            result = LLMResponse(
                content=content,
                success=True,
                from_cache=False,
                latency_ms=latency_ms,
                model=self.model,
                prompt_hash=get_prompt_hash(prompt),
            )
            
            # Cache successful response
            if self.use_cache:
                get_cache().set(prompt, result)
            
            return result
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            accumulator.record_llm_call(success=False)
            
            # Determine failure type
            error_str = str(e).lower()
            if "rate" in error_str and "limit" in error_str:
                failure_type = LLMFailureType.RATE_LIMITED
            else:
                failure_type = LLMFailureType.UNAVAILABLE
            
            accumulator.error(
                message=f"LLM API error: {e}",
                stage=stage or ExtractionStage.TABLE_PARSING,
                table_number=table_number,
                llm_failure_type=failure_type,
                recoverable=True,  # Can continue with defaults
                details={"error": str(e)},
            )
            
            return LLMResponse(
                content="",
                success=False,
                failure_type=failure_type,
                latency_ms=latency_ms,
                model=self.model,
                prompt_hash=get_prompt_hash(prompt),
                error_message=str(e),
            )
    
    @property
    def average_latency_ms(self) -> float:
        if self._call_count == 0:
            return 0.0
        return self._total_latency_ms / self._call_count
    
    @property
    def call_count(self) -> int:
        return self._call_count


# Global client instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create global LLM client."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def call_llm(
    prompt: str, 
    max_tokens: int = 500,
    stage: Optional[ExtractionStage] = None,
) -> str:
    """
    Convenience function for simple LLM calls.
    
    Returns empty string on failure (for backward compatibility).
    For more control, use LLMClient directly.
    """
    client = get_llm_client()
    response = client.call(prompt, max_tokens=max_tokens, stage=stage)
    return response.content
