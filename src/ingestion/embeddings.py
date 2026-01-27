"""
DevChat v2.0 SOTA - Embedding Generation

Supports multiple embedding providers:
- Cohere embed-v4 (recommended)
- OpenAI text-embedding-3-large
- Voyage AI voyage-3-large
- Local models via HuggingFace

Features:
- Embedding caching (50-80% cost reduction on re-indexing)
- Batch processing with progress bars
- Provider-specific optimizations
"""

from enum import Enum
from typing import List, Optional

from llama_index.core.schema import BaseNode

from src.config.settings import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class EmbeddingProvider(str, Enum):
    """Supported embedding providers."""
    COHERE = "cohere"
    OPENAI = "openai"
    VOYAGE = "voyage"
    HUGGINGFACE = "huggingface"


class EmbeddingGenerator:
    """
    Generate embeddings using various providers.
    
    Default: Cohere embed-v4 (best performance for retrieval)
    """
    
    def __init__(
        self,
        provider: str = settings.embedding_provider,
        model: str = settings.embedding_model,
    ):
        self.provider = EmbeddingProvider(provider)
        self.model = model
        self._embed_model = None
        
    def get_embed_model(self):
        """
        Get the embedding model instance.
        
        Returns:
            LlamaIndex embedding model
        """
        if self._embed_model is not None:
            return self._embed_model
        
        if self.provider == EmbeddingProvider.COHERE:
            self._embed_model = self._get_cohere_model()
        elif self.provider == EmbeddingProvider.OPENAI:
            self._embed_model = self._get_openai_model()
        elif self.provider == EmbeddingProvider.VOYAGE:
            self._embed_model = self._get_voyage_model()
        elif self.provider == EmbeddingProvider.HUGGINGFACE:
            self._embed_model = self._get_huggingface_model()
        else:
            raise ValueError(f"Unknown embedding provider: {self.provider}")
        
        logger.info(f"Initialized embedding model: {self.provider.value}/{self.model}")
        return self._embed_model
    
    def _get_cohere_model(self):
        """Get Cohere embedding model."""
        try:
            from llama_index.embeddings.cohere import CohereEmbedding
        except ImportError:
            raise ImportError(
                "Cohere embeddings not installed. "
                "Run: pip install llama-index-embeddings-cohere"
            )
        
        return CohereEmbedding(
            model_name=self.model,
            api_key=settings.cohere_api_key,
            input_type=settings.embedding_input_type,
        )
    
    def _get_openai_model(self):
        """Get OpenAI embedding model."""
        try:
            from llama_index.embeddings.openai import OpenAIEmbedding
        except ImportError:
            raise ImportError(
                "OpenAI embeddings not installed. "
                "Run: pip install llama-index-embeddings-openai"
            )
        
        return OpenAIEmbedding(
            model=self.model,
            api_key=settings.openai_api_key,
        )
    
    def _get_voyage_model(self):
        """Get Voyage AI embedding model."""
        try:
            from llama_index.embeddings.voyageai import VoyageEmbedding
        except ImportError:
            raise ImportError(
                "Voyage AI embeddings not installed. "
                "Run: pip install llama-index-embeddings-voyageai"
            )
        
        return VoyageEmbedding(
            model_name=self.model,
            voyage_api_key=settings.voyage_api_key,
        )
    
    def _get_huggingface_model(self):
        """Get HuggingFace local embedding model."""
        try:
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        except ImportError:
            raise ImportError(
                "HuggingFace embeddings not installed. "
                "Run: pip install llama-index-embeddings-huggingface"
            )
        
        return HuggingFaceEmbedding(model_name=self.model)
    
    def embed_texts(self, texts: List[str], use_cache: bool = True) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            use_cache: Whether to use embedding cache (default: True)
            
        Returns:
            List of embedding vectors
        """
        if use_cache and settings.embedding_cache_enabled:
            from src.utils.embedding_cache import cached_embed_texts
            
            embed_model = self.get_embed_model()
            
            return cached_embed_texts(
                texts=texts,
                embed_fn=lambda t: embed_model.get_text_embedding_batch(t),
                model_name=self.model,
            )
        else:
            embed_model = self.get_embed_model()
            embeddings = embed_model.get_text_embedding_batch(texts)
            return embeddings
    
    def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a query.
        
        Note: Some providers use different models for queries vs documents.
        
        Args:
            query: Query text
            
        Returns:
            Embedding vector
        """
        embed_model = self.get_embed_model()
        
        # For Cohere, switch input type to search_query
        if self.provider == EmbeddingProvider.COHERE:
            # Create a query-specific embedding
            from llama_index.embeddings.cohere import CohereEmbedding
            query_embed = CohereEmbedding(
                model_name=self.model,
                api_key=settings.cohere_api_key,
                input_type="search_query",
            )
            return query_embed.get_text_embedding(query)
        
        return embed_model.get_text_embedding(query)
    
    def embed_nodes(
        self,
        nodes: List[BaseNode],
        show_progress: bool = True,
    ) -> List[BaseNode]:
        """
        Add embeddings to nodes.
        
        Args:
            nodes: List of nodes to embed
            show_progress: Whether to show progress bar
            
        Returns:
            Nodes with embeddings added
        """
        from tqdm import tqdm
        
        embed_model = self.get_embed_model()
        
        # Extract texts
        texts = [node.get_content() for node in nodes]
        
        # Batch embed
        batch_size = 100
        all_embeddings = []
        
        iterator = range(0, len(texts), batch_size)
        if show_progress:
            iterator = tqdm(iterator, desc="Generating embeddings")
        
        for i in iterator:
            batch_texts = texts[i:i + batch_size]
            batch_embeddings = embed_model.get_text_embedding_batch(batch_texts)
            all_embeddings.extend(batch_embeddings)
        
        # Attach embeddings to nodes
        for node, embedding in zip(nodes, all_embeddings):
            node.embedding = embedding
        
        logger.info(f"Generated embeddings for {len(nodes)} nodes")
        return nodes


def get_embedding_model():
    """
    Get the default embedding model instance.
    
    Convenience function that creates an EmbeddingGenerator and returns
    the underlying embed model.
    
    Returns:
        LlamaIndex embedding model
    """
    generator = EmbeddingGenerator()
    return generator.get_embed_model()


def get_embedding_dimension(provider: str = settings.embedding_provider) -> int:
    """
    Get the embedding dimension for a provider.
    
    Returns:
        Embedding dimension size
    """
    dimensions = {
        "cohere": 1536,  # embed-v4.0 default dimension
        "openai": 3072,  # text-embedding-3-large
        "voyage": 1024,  # voyage-3
        "huggingface": 768,  # varies by model
    }
    return dimensions.get(provider, settings.embedding_dimension)
