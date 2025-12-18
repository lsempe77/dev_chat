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
    openai_api_key: str = Field(default="", description="OpenAI API key (fallback)")
    cohere_api_key: str = Field(default="", description="Cohere API key for embeddings/rerank")
    voyage_api_key: Optional[str] = Field(default=None, description="Voyage AI API key")
    
    # =========================================================================
    # Vector Database
    # =========================================================================
    qdrant_url: str = Field(default="http://localhost:6333", description="Qdrant server URL")
    qdrant_api_key: Optional[str] = Field(default=None, description="Qdrant API key (for cloud)")
    qdrant_collection_name: str = Field(default="devchat_v2", description="Qdrant collection name")
    
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
    
    # =========================================================================
    # Reranking
    # =========================================================================
    rerank_enabled: bool = Field(default=True)
    rerank_model: str = Field(default="rerank-v3.5")
    rerank_top_n: int = Field(default=15, ge=1)
    
    # =========================================================================
    # Retrieval
    # =========================================================================
    hybrid_enabled: bool = Field(default=True, description="Enable hybrid search")
    hybrid_alpha: float = Field(
        default=0.7, 
        ge=0.0, 
        le=1.0,
        description="Dense vs Sparse weight (1.0 = pure dense)"
    )
    retrieval_top_k: int = Field(default=50, ge=1, description="Initial retrieval count")
    final_top_k: int = Field(default=10, ge=1, description="Final context chunks")
    
    # =========================================================================
    # Chunking
    # =========================================================================
    chunk_size: int = Field(default=512, ge=100)
    chunk_overlap: int = Field(default=50, ge=0)
    parent_chunk_size: int = Field(default=2048, ge=256)
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
