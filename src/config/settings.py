"""
DevChat v2.0 SOTA - Settings Configuration

Centralized configuration management using Pydantic Settings.
All settings can be overridden via environment variables.
"""

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Application environment."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(str, Enum):
    """Logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENROUTER = "openrouter"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class Settings(BaseSettings):
    """
    Application settings with environment variable support.
    
    All settings can be overridden via environment variables.
    Example: ANTHROPIC_API_KEY=sk-xxx
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # =========================================================================
    # API Keys
    # =========================================================================
    openrouter_api_key: str = Field(default="", description="OpenRouter API key (unified access to all models)")
    anthropic_api_key: str = Field(default="", description="Anthropic API key for Claude (fallback)")
    admin_api_key: str = Field(default="", description="Admin API key for programmatic /admin access")
    admin_password: str = Field(default="", description="Admin password for browser login to /admin")
    openai_api_key: str = Field(default="", description="OpenAI API key (fallback)")
    cohere_api_key: str = Field(default="", description="Cohere API key for embeddings/rerank")
    voyage_api_key: Optional[str] = Field(default=None, description="Voyage AI API key")
    
    # =========================================================================
    # Supabase (Multi-Tenant Auth & Database)
    # =========================================================================
    supabase_url: str = Field(default="", description="Supabase project URL")
    supabase_anon_key: str = Field(default="", description="Supabase anonymous/public key")
    supabase_service_role_key: str = Field(default="", description="Supabase service role key (backend only)")
    supabase_jwt_secret: str = Field(default="", description="Supabase JWT secret for token verification")
    
    # =========================================================================
    # Vector Database
    # =========================================================================
    qdrant_url: str = Field(default="http://localhost:6333", description="Qdrant server URL")
    qdrant_api_key: Optional[str] = Field(default=None, description="Qdrant API key (for cloud)")
    qdrant_collection_name: str = Field(default="devchat_v2_contextual", description="SOTA collection: Hybrid BM25+Dense, Contextual Prefixes")
    
    # =========================================================================
    # Observability
    # =========================================================================
    langfuse_public_key: Optional[str] = Field(default=None, description="Langfuse public key")
    langfuse_secret_key: Optional[str] = Field(default=None, description="Langfuse secret key")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", description="Langfuse host")
    
    # =========================================================================
    # Application
    # =========================================================================
    environment: Environment = Field(default=Environment.DEVELOPMENT)
    log_level: LogLevel = Field(default=LogLevel.INFO)
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    
    # =========================================================================
    # LLM Models (via OpenRouter)
    # =========================================================================
    llm_provider: LLMProvider = Field(default=LLMProvider.OPENROUTER)
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL"
    )
    # Model names use OpenRouter format: provider/model-name
    # Using OpenAI models for better rate limits - Claude also available:
    # - anthropic/claude-3-5-haiku-20241022 (fast)
    # - anthropic/claude-sonnet-4-20250514 (reasoning)
    llm_fast_model: str = Field(
        default="openai/gpt-4o-mini",
        description="Fast model for simple tasks (via OpenRouter)"
    )
    llm_reasoning_model: str = Field(
        default="openai/gpt-4o",
        description="Reasoning model for complex synthesis (via OpenRouter)"
    )
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=4096, ge=1)
    
    # =========================================================================
    # Embeddings
    # =========================================================================
    embedding_provider: str = Field(
        default="cohere",
        description="Embedding provider: 'cohere' or 'voyage'"
    )
    embedding_model: str = Field(
        default="embed-v4.0",
        description="Cohere: 'embed-v4.0' | Voyage: 'voyage-3' or 'voyage-3-lite'"
    )
    embedding_dimension: int = Field(default=1536)
    embedding_input_type: str = Field(default="search_document")
    
    # Embedding Cache (50-80% cost reduction on re-indexing)
    embedding_cache_enabled: bool = Field(
        default=True,
        description="Enable embedding cache to reduce API costs"
    )
    embedding_cache_dir: str = Field(
        default=".cache/embeddings",
        description="Directory for embedding cache files"
    )
    embedding_cache_ttl_days: int = Field(
        default=30,
        ge=1,
        description="Cache TTL in days"
    )
    
    # =========================================================================
    # Reranking (Cohere v3.5)
    # =========================================================================
    rerank_enabled: bool = Field(default=True)
    rerank_model: str = Field(default="rerank-v3.5")
    
    # =========================================================================
    # Retrieval (SOTA 2025: Contextual Retrieval + Hybrid + Reranking)
    # =========================================================================
    hybrid_enabled: bool = Field(default=True, description="Enable hybrid search BM25+Dense (Anthropic: 49% improvement)")
    hybrid_alpha: float = Field(
        default=0.7, 
        ge=0.0, 
        le=1.0,
        description="Dense vs Sparse weight (1.0 = pure dense, 0.7 recommended)"
    )
    retrieval_top_k: int = Field(default=150, ge=1, description="Initial retrieval count (retrieve more, rerank down)")
    rerank_top_n: int = Field(default=20, ge=1)  # Moved here for clarity
    final_top_k: int = Field(default=20, ge=1, description="Final context chunks (Anthropic: 20 is optimal)")
    
    # Retrieval Quality Metrics (logged to Langfuse)
    retrieval_metrics_enabled: bool = Field(
        default=True,
        description="Track Recall@K, NDCG, MRR for retrieval quality monitoring"
    )
    
    # Contextual Retrieval (Anthropic: 67% improvement with reranking)
    contextual_retrieval_enabled: bool = Field(default=True, description="Prepend document context to chunks")
    contextual_mode: str = Field(default="fast", description="'fast' (metadata-only) or 'llm' (AI-generated)")
    
    # =========================================================================
    # Chunking (256 words = better precision for RAG retrieval)
    # =========================================================================
    chunk_size: int = Field(default=256, ge=100)
    chunk_overlap: int = Field(default=50, ge=0)
    parent_chunk_size: int = Field(default=1024, ge=256)  # Parent = 4x child
    use_semantic_chunking: bool = Field(default=True)
    
    # =========================================================================
    # Data Paths
    # =========================================================================
    data_dir: Path = Field(default=Path("./data"))
    markdown_dir: Path = Field(default=Path("./data/markdown"))
    metadata_file: Path = Field(default=Path("./data/metadata.csv"))
    
    # =========================================================================
    # PDF Source Configuration (Placeholder)
    # =========================================================================
    # TODO: Implement metadata linking to PDFs
    # SharePoint URL: https://3ie.sharepoint.com/:f:/s/DEPChatbot/IgCdLWmj1g8OR5L-m5ikM-dfAZN8J2CFCpv_B5EPwZKy28o?e=hB8isv
    pdf_source_url: str = Field(
        default="",
        description="Base URL for PDF source files (SharePoint or other storage)"
    )
    pdf_metadata_mapping_file: Path = Field(
        default=Path("./data/pdf_metadata_mapping.json"),
        description="JSON file mapping study IDs to PDF URLs"
    )
    
    # =========================================================================
    # Query Processing
    # =========================================================================
    query_expansion_enabled: bool = Field(default=True)
    query_classification_enabled: bool = Field(default=True)
    
    # Multi-Query RAG-Fusion (RAG-Fusion paper, 2024)
    # Generates query variants → retrieves for each → RRF fusion
    # Improves recall by 10-15% by capturing different phrasings
    multi_query_enabled: bool = Field(
        default=True,
        description="Enable multi-query RAG-Fusion for improved recall"
    )
    multi_query_num_variants: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Number of query variants to generate (excluding original)"
    )
    
    # HyDE: Hypothetical Document Embeddings (Gao et al. 2022)
    # Generates a hypothetical answer to use for retrieval instead of the raw query
    # NOTE: Disabled after testing - HyDE hurts faithfulness in this domain
    # (likely because generated hypothetical answers introduce biases)
    hyde_enabled: bool = Field(
        default=False, 
        description="Enable HyDE query enhancement (disabled - hurts faithfulness)"
    )
    
    # Conversation Memory
    conversation_memory_enabled: bool = Field(
        default=True,
        description="Enable persistent conversation memory across sessions"
    )
    max_conversation_history: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum messages to include in conversation context"
    )
    
    # Knowledge Graph (Neo4j)
    knowledge_graph_enabled: bool = Field(
        default=False,  # Disabled by default - requires Neo4j setup
        description="Enable knowledge graph for relationship-based retrieval"
    )
    graph_llm_extraction_enabled: bool = Field(
        default=False,
        description="Use LLM to extract entities from document content (slower but richer)"
    )
    
    # =========================================================================
    # Production Scaling & Performance
    # =========================================================================
    # Max sources to process in structured synthesizer (prevents timeout with large corpus)
    max_sources_for_extraction: int = Field(
        default=8, 
        ge=1, 
        le=20,
        description="Maximum sources to process for per-source evidence extraction"
    )
    # Concurrency for LLM calls (prevents rate limiting and reduces total time)
    llm_concurrency_limit: int = Field(
        default=4,
        ge=1,
        le=10,
        description="Max concurrent LLM API calls"
    )
    # Request timeout in seconds
    request_timeout_seconds: int = Field(
        default=120,
        ge=30,
        le=300,
        description="Maximum time for a single query request"
    )
    # Enable response caching
    enable_response_cache: bool = Field(
        default=True,
        description="Cache query responses for identical queries"
    )
    response_cache_ttl_seconds: int = Field(
        default=3600,
        description="Time-to-live for cached responses in seconds"
    )
    
    # Semantic cache settings
    semantic_cache_enabled: bool = Field(
        default=True,
        description="Enable semantic similarity matching for cache (matches similar queries)"
    )
    semantic_cache_threshold: float = Field(
        default=0.95,
        ge=0.8,
        le=1.0,
        description="Minimum cosine similarity threshold for semantic cache match (0.8-1.0)"
    )
    
    # Query decomposition settings
    query_decomposition_enabled: bool = Field(
        default=True,
        description="Enable query decomposition for complex queries (comparisons, multi-aspect)"
    )
    
    # Step-back prompting settings
    step_back_prompting_enabled: bool = Field(
        default=True,
        description="Enable step-back prompting for specific questions (ask general question first)"
    )
    
    # =========================================================================
    # Validators
    # =========================================================================
    
    @field_validator("chunk_overlap")
    @classmethod
    def validate_chunk_overlap(cls, v: int, info) -> int:
        """Ensure chunk overlap is less than chunk size."""
        chunk_size = info.data.get("chunk_size", 512)
        if v >= chunk_size:
            raise ValueError(f"chunk_overlap ({v}) must be less than chunk_size ({chunk_size})")
        return v
    
    @field_validator("data_dir", "markdown_dir", "metadata_file", mode="before")
    @classmethod
    def resolve_path(cls, v: str | Path) -> Path:
        """Convert string paths to Path objects."""
        return Path(v) if isinstance(v, str) else v
    
    # =========================================================================
    # Properties
    # =========================================================================
    
    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == Environment.PRODUCTION
    
    @property
    def langfuse_enabled(self) -> bool:
        """Check if Langfuse tracing is configured."""
        return bool(self.langfuse_public_key and self.langfuse_secret_key)
    
    @property
    def sparse_weight(self) -> float:
        """Calculate sparse search weight from hybrid_alpha."""
        return 1.0 - self.hybrid_alpha


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Uses LRU cache to avoid re-reading .env file on every call.
    Call get_settings.cache_clear() to reload settings.
    """
    return Settings()


# Convenience alias
settings = get_settings()
