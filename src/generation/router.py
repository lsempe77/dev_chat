"""
DevChat v2.0 SOTA - Model Router

Adaptive routing to select the appropriate LLM based on query complexity.
Uses OpenRouter for unified access to multiple LLM providers.
- Simple queries -> Fast model (Claude 3.5 Haiku)
- Complex synthesis -> Reasoning model (Claude Sonnet 4)

OpenRouter model format: provider/model-name
Examples:
- anthropic/claude-3-5-haiku-20241022
- anthropic/claude-sonnet-4-20250514
- openai/gpt-4o
- google/gemini-2.0-flash-exp
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.config.settings import settings, LLMProvider
from src.retrieval.query_processor import QueryType
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ModelTier(str, Enum):
    """LLM model tiers."""
    FAST = "fast"
    REASONING = "reasoning"


@dataclass
class RoutingDecision:
    """Result of model routing decision."""
    tier: ModelTier
    model_name: str
    reason: str
    estimated_cost_factor: float = 1.0


class ModelRouter:
    """
    Route queries to appropriate LLM based on complexity.
    
    Factors considered:
    - Query type (simple, synthesis, comparison)
    - Context size
    - Expected response complexity
    """
    
    def __init__(
        self,
        fast_model: str = settings.llm_fast_model,
        reasoning_model: str = settings.llm_reasoning_model,
    ):
        self.fast_model = fast_model
        self.reasoning_model = reasoning_model
        
        # Cache LLM instances
        self._llms = {}
    
    def route(
        self,
        query_type: QueryType,
        context_length: int = 0,
        num_studies: int = 0,
    ) -> RoutingDecision:
        """
        Determine which model to use.
        
        Args:
            query_type: Classified query type
            context_length: Length of retrieved context
            num_studies: Number of studies in context
            
        Returns:
            RoutingDecision with model selection
        """
        # Simple queries -> fast model
        if query_type == QueryType.SIMPLE:
            return RoutingDecision(
                tier=ModelTier.FAST,
                model_name=self.fast_model,
                reason="Simple factual query",
                estimated_cost_factor=1.0,
            )
        
        # Large context -> reasoning model
        if context_length > 6000:
            return RoutingDecision(
                tier=ModelTier.REASONING,
                model_name=self.reasoning_model,
                reason="Large context requires stronger model",
                estimated_cost_factor=10.0,
            )
        
        # Lookup queries -> fast model (unless many results)
        if query_type == QueryType.LOOKUP and num_studies <= 5:
            return RoutingDecision(
                tier=ModelTier.FAST,
                model_name=self.fast_model,
                reason="Study lookup with few results",
                estimated_cost_factor=1.0,
            )
        
        # Comparison queries -> always reasoning model
        if query_type == QueryType.COMPARISON:
            return RoutingDecision(
                tier=ModelTier.REASONING,
                model_name=self.reasoning_model,
                reason="Comparison requires nuanced analysis",
                estimated_cost_factor=10.0,
            )
        
        # Synthesis with many studies -> reasoning model
        if query_type == QueryType.SYNTHESIS and num_studies > 3:
            return RoutingDecision(
                tier=ModelTier.REASONING,
                model_name=self.reasoning_model,
                reason=f"Synthesis across {num_studies} studies",
                estimated_cost_factor=10.0,
            )
        
        # Default to fast model
        return RoutingDecision(
            tier=ModelTier.FAST,
            model_name=self.fast_model,
            reason="Default routing",
            estimated_cost_factor=1.0,
        )
    
    def get_llm(self, decision: RoutingDecision):
        """
        Get the LLM instance for a routing decision.
        
        Args:
            decision: Routing decision
            
        Returns:
            LlamaIndex LLM instance
        """
        model_name = decision.model_name
        
        if model_name in self._llms:
            return self._llms[model_name]
        
        # Create LLM instance
        llm = self._create_llm(model_name)
        self._llms[model_name] = llm
        
        return llm
    
    def _create_llm(self, model_name: str):
        """Create LLM instance based on provider setting."""
        # Use OpenRouter if configured (default)
        if settings.llm_provider == LLMProvider.OPENROUTER:
            return self._create_openrouter_llm(model_name)
        
        # Fallback to direct provider APIs
        if "claude" in model_name.lower():
            return self._create_anthropic_llm(model_name)
        elif "gpt" in model_name.lower() or "o1" in model_name.lower():
            return self._create_openai_llm(model_name)
        else:
            # Default to OpenRouter
            return self._create_openrouter_llm(model_name)
    
    def _create_openrouter_llm(self, model_name: str):
        """
        Create OpenRouter LLM.
        
        OpenRouter provides unified access to multiple LLM providers
        with a single API key. Models are specified as provider/model-name.
        
        Docs: https://openrouter.ai/docs
        """
        try:
            from llama_index.llms.openai_like import OpenAILike
            
            # OpenAILike doesn't validate model names, perfect for OpenRouter
            return OpenAILike(
                model=model_name,
                api_key=settings.openrouter_api_key,
                api_base=settings.openrouter_base_url,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                is_chat_model=True,
                additional_kwargs={
                    "extra_headers": {
                        "HTTP-Referer": "https://3ieimpact.org",
                        "X-Title": "DevChat 3ie",
                    }
                }
            )
        except ImportError:
            raise ImportError(
                "OpenAI-like LLM not installed. "
                "Run: pip install llama-index-llms-openai-like"
            )
    
    def _create_anthropic_llm(self, model_name: str):
        """Create Anthropic LLM (direct API, fallback)."""
        try:
            from llama_index.llms.anthropic import Anthropic
            
            # Extract model name if in OpenRouter format (provider/model)
            if "/" in model_name:
                model_name = model_name.split("/")[-1]
            
            return Anthropic(
                model=model_name,
                api_key=settings.anthropic_api_key,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
        except ImportError:
            raise ImportError(
                "Anthropic LLM not installed. "
                "Run: pip install llama-index-llms-anthropic"
            )
    
    def _create_openai_llm(self, model_name: str):
        """Create OpenAI LLM (direct API, fallback)."""
        try:
            from llama_index.llms.openai import OpenAI
            
            # Extract model name if in OpenRouter format (provider/model)
            if "/" in model_name:
                model_name = model_name.split("/")[-1]
            
            return OpenAI(
                model=model_name,
                api_key=settings.openai_api_key,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
        except ImportError:
            raise ImportError(
                "OpenAI LLM not installed. "
                "Run: pip install llama-index-llms-openai"
            )


class CostTracker:
    """
    Track LLM usage costs.
    
    Approximate costs per 1M tokens (as of Dec 2025).
    OpenRouter adds a small markup (~5-10%) on top of provider costs.
    
    Model names support both direct and OpenRouter formats:
    - "claude-3-5-haiku-20241022" (direct)
    - "anthropic/claude-3-5-haiku-20241022" (OpenRouter)
    """
    
    # Costs per 1M tokens (input, output) - OpenRouter prices
    COSTS = {
        # Anthropic via OpenRouter
        "anthropic/claude-3-5-haiku-20241022": (0.80, 4.0),
        "anthropic/claude-sonnet-4-20250514": (3.0, 15.0),
        "anthropic/claude-3-5-sonnet-20241022": (3.0, 15.0),
        # Direct Anthropic names (fallback)
        "claude-3-5-haiku-20241022": (0.80, 4.0),
        "claude-sonnet-4-20250514": (3.0, 15.0),
        # OpenAI via OpenRouter
        "openai/gpt-4o-mini": (0.15, 0.60),
        "openai/gpt-4o": (2.50, 10.0),
        "openai/gpt-4.1": (2.0, 8.0),
        "openai/gpt-4.1-mini": (0.40, 1.60),
        # Direct OpenAI names (fallback)
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4o": (2.50, 10.0),
        "gpt-4.1": (2.0, 8.0),
        "gpt-4.1-mini": (0.40, 1.60),
        # Google via OpenRouter
        "google/gemini-2.0-flash-exp": (0.10, 0.40),
        "google/gemini-pro-1.5": (1.25, 5.0),
    }
    
    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0
        self.calls = []
    
    def track(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """
        Track a single LLM call.
        
        Returns estimated cost in USD.
        """
        input_cost, output_cost = self.COSTS.get(model, (1.0, 4.0))
        
        cost = (
            (input_tokens / 1_000_000) * input_cost +
            (output_tokens / 1_000_000) * output_cost
        )
        
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost += cost
        
        self.calls.append({
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
        })
        
        return cost
    
    def get_summary(self) -> dict:
        """Get usage summary."""
        return {
            "total_calls": len(self.calls),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost, 4),
        }
