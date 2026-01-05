"""
DevChat v2.0 SOTA - Cost Configuration

Pricing per 1M tokens for each model/provider.
Updated: January 2026

Sources:
- OpenRouter: https://openrouter.ai/docs#models
- Cohere: https://cohere.com/pricing
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Optional


@dataclass
class ModelPricing:
    """Pricing for a single model."""
    input_per_1m: Decimal  # Cost per 1M input tokens
    output_per_1m: Decimal  # Cost per 1M output tokens
    provider: str
    
    def calculate_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        """Calculate cost for given token usage."""
        input_cost = (Decimal(input_tokens) / Decimal(1_000_000)) * self.input_per_1m
        output_cost = (Decimal(output_tokens) / Decimal(1_000_000)) * self.output_per_1m
        return input_cost + output_cost


# Model pricing configuration (USD per 1M tokens)
# Updated January 2026 - verify against provider pricing pages
MODEL_PRICING: Dict[str, ModelPricing] = {
    # OpenRouter / OpenAI models
    "openai/gpt-4o": ModelPricing(
        input_per_1m=Decimal("2.50"),
        output_per_1m=Decimal("10.00"),
        provider="openrouter"
    ),
    "openai/gpt-4o-mini": ModelPricing(
        input_per_1m=Decimal("0.15"),
        output_per_1m=Decimal("0.60"),
        provider="openrouter"
    ),
    "gpt-4o": ModelPricing(
        input_per_1m=Decimal("2.50"),
        output_per_1m=Decimal("10.00"),
        provider="openai"
    ),
    "gpt-4o-mini": ModelPricing(
        input_per_1m=Decimal("0.15"),
        output_per_1m=Decimal("0.60"),
        provider="openai"
    ),
    
    # Anthropic models (via OpenRouter)
    "anthropic/claude-sonnet-4-20250514": ModelPricing(
        input_per_1m=Decimal("3.00"),
        output_per_1m=Decimal("15.00"),
        provider="openrouter"
    ),
    "anthropic/claude-3-5-haiku-20241022": ModelPricing(
        input_per_1m=Decimal("0.80"),
        output_per_1m=Decimal("4.00"),
        provider="openrouter"
    ),
    "anthropic/claude-3-5-sonnet-20241022": ModelPricing(
        input_per_1m=Decimal("3.00"),
        output_per_1m=Decimal("15.00"),
        provider="openrouter"
    ),
    
    # Google models (via OpenRouter) - Free tier
    "google/gemini-2.0-flash-exp": ModelPricing(
        input_per_1m=Decimal("0"),
        output_per_1m=Decimal("0"),
        provider="openrouter"
    ),
    "google/gemini-exp-1206": ModelPricing(
        input_per_1m=Decimal("0"),
        output_per_1m=Decimal("0"),
        provider="openrouter"
    ),
    
    # Cohere models
    "embed-v4": ModelPricing(
        input_per_1m=Decimal("0.10"),
        output_per_1m=Decimal("0"),
        provider="cohere"
    ),
    "embed-english-v3.0": ModelPricing(
        input_per_1m=Decimal("0.10"),
        output_per_1m=Decimal("0"),
        provider="cohere"
    ),
    "rerank-v3.5": ModelPricing(
        input_per_1m=Decimal("2.00"),
        output_per_1m=Decimal("0"),
        provider="cohere"
    ),
    "rerank-english-v3.0": ModelPricing(
        input_per_1m=Decimal("2.00"),
        output_per_1m=Decimal("0"),
        provider="cohere"
    ),
}

# Aliases for common model names
MODEL_ALIASES: Dict[str, str] = {
    "gpt-4o": "openai/gpt-4o",
    "gpt-4o-mini": "openai/gpt-4o-mini",
    "gpt-4-turbo": "openai/gpt-4o",  # Treat as gpt-4o for costing
    "claude-sonnet-4": "anthropic/claude-sonnet-4-20250514",
    "claude-sonnet-4-20250514": "anthropic/claude-sonnet-4-20250514",
    "claude-3-5-haiku-20241022": "anthropic/claude-3-5-haiku-20241022",
    "claude-3-5-sonnet-20241022": "anthropic/claude-3-5-sonnet-20241022",
    "claude-3.5-haiku": "anthropic/claude-3-5-haiku-20241022",
    "gemini-2.0-flash-exp": "google/gemini-2.0-flash-exp",
    "gemini-exp-1206": "google/gemini-exp-1206",
}


def get_model_pricing(model: str) -> Optional[ModelPricing]:
    """Get pricing for a model, handling aliases."""
    # Check direct match
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    
    # Check aliases
    if model in MODEL_ALIASES:
        return MODEL_PRICING.get(MODEL_ALIASES[model])
    
    # Check partial matches (e.g., "gpt-4o" in "openai/gpt-4o")
    for key, pricing in MODEL_PRICING.items():
        if model in key or key in model:
            return pricing
    
    return None


def calculate_cost(model: str, input_tokens: int, output_tokens: int = 0) -> Decimal:
    """
    Calculate cost for a model call.
    
    Args:
        model: Model name (e.g., "gpt-4o", "openai/gpt-4o-mini", "embed-v4")
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens (0 for embeddings)
    
    Returns:
        Cost in USD as Decimal
    """
    pricing = get_model_pricing(model)
    if pricing is None:
        # Unknown model - return 0 but log warning
        return Decimal("0")
    
    return pricing.calculate_cost(input_tokens, output_tokens)


# Quick reference for common operations
ESTIMATED_COSTS = {
    "single_query_gpt4o": Decimal("0.02"),  # ~2000 input + 500 output tokens
    "single_query_mini": Decimal("0.001"),  # ~2000 input + 500 output tokens
    "embed_1000_chunks": Decimal("0.10"),   # ~100k tokens
    "rerank_100_docs": Decimal("0.02"),     # ~10k tokens
}
