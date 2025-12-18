"""
DevChat v2.0 SOTA - Reranking

Cross-encoder reranking for precision improvement.
Supports:
- Cohere Rerank v3.5 (recommended)
- Voyage Rerank
- Local models (BGE-Reranker)
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.config.settings import settings
from src.retrieval.hybrid_retriever import RetrievalResult
from src.utils.logging import get_logger

logger = get_logger(__name__)


class Reranker(ABC):
    """Abstract base class for rerankers."""
    
    @abstractmethod
    async def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_n: int,
    ) -> List[RetrievalResult]:
        """
        Rerank retrieval results.
        
        Args:
            query: Original query
            results: Retrieved results to rerank
            top_n: Number of top results to return
            
        Returns:
            Reranked results
        """
        pass


class CohereReranker(Reranker):
    """
    Cohere Rerank v3.5 - SOTA cross-encoder reranking.
    
    Significantly improves retrieval precision by scoring
    each document against the query with a cross-encoder.
    """
    
    def __init__(
        self,
        model: str = settings.rerank_model,
        api_key: Optional[str] = None,
    ):
        self.model = model
        self.api_key = api_key or settings.cohere_api_key
        self._client = None
    
    def _get_client(self):
        """Get or create Cohere client."""
        if self._client is None:
            try:
                import cohere
                self._client = cohere.ClientV2(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "Cohere not installed. Run: pip install cohere"
                )
        return self._client
    
    async def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_n: int = settings.rerank_top_n,
    ) -> List[RetrievalResult]:
        """Rerank using Cohere Rerank."""
        if not results:
            return results
        
        if not self.api_key:
            logger.warning("Cohere API key not set, skipping reranking")
            return results[:top_n]
        
        try:
            client = self._get_client()
            
            # Prepare documents
            documents = [r.text for r in results]
            
            # Call Cohere Rerank V2 API
            # Note: V2 API doesn't have return_documents parameter
            response = client.rerank(
                model=self.model,
                query=query,
                documents=documents,
                top_n=top_n,
            )
            
            # Reorder results based on reranking
            reranked = []
            for item in response.results:
                original_result = results[item.index]
                # Update score with rerank score
                reranked.append(RetrievalResult(
                    node_id=original_result.node_id,
                    text=original_result.text,
                    score=item.relevance_score,
                    metadata=original_result.metadata,
                    parent_text=original_result.parent_text,
                ))
            
            logger.info(
                f"Reranked {len(results)} → {len(reranked)} results "
                f"(top score: {reranked[0].score:.3f})"
            )
            
            return reranked
            
        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            return results[:top_n]
    
    def rerank_sync(
        self,
        query: str,
        results: List[RetrievalResult],
        top_n: int = settings.rerank_top_n,
    ) -> List[RetrievalResult]:
        """Synchronous reranking."""
        import asyncio
        return asyncio.run(self.rerank(query, results, top_n))


class LlamaIndexCohereReranker(Reranker):
    """
    Cohere reranker using LlamaIndex integration.
    
    Useful when working within LlamaIndex pipelines.
    """
    
    def __init__(
        self,
        model: str = settings.rerank_model,
        top_n: int = settings.rerank_top_n,
    ):
        self.model = model
        self.top_n = top_n
        self._reranker = None
    
    def _get_reranker(self):
        """Get LlamaIndex Cohere reranker."""
        if self._reranker is None:
            try:
                from llama_index.postprocessor.cohere_rerank import CohereRerank
                self._reranker = CohereRerank(
                    model=self.model,
                    top_n=self.top_n,
                    api_key=settings.cohere_api_key,
                )
            except ImportError:
                raise ImportError(
                    "LlamaIndex Cohere rerank not installed. "
                    "Run: pip install llama-index-postprocessor-cohere-rerank"
                )
        return self._reranker
    
    async def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_n: int = None,
    ) -> List[RetrievalResult]:
        """Rerank using LlamaIndex Cohere integration."""
        # Convert to LlamaIndex nodes for compatibility
        from llama_index.core.schema import NodeWithScore, TextNode
        
        nodes = [
            NodeWithScore(
                node=TextNode(
                    text=r.text,
                    metadata=r.metadata,
                    id_=r.node_id,
                ),
                score=r.score,
            )
            for r in results
        ]
        
        # Rerank
        reranker = self._get_reranker()
        from llama_index.core.schema import QueryBundle
        reranked_nodes = reranker.postprocess_nodes(
            nodes,
            query_bundle=QueryBundle(query_str=query),
        )
        
        # Convert back
        return [
            RetrievalResult(
                node_id=n.node.node_id,
                text=n.node.text,
                score=n.score or 0.0,
                metadata=n.node.metadata,
            )
            for n in reranked_nodes
        ]


class LocalReranker(Reranker):
    """
    Local cross-encoder reranking using HuggingFace models.
    
    Models:
    - BAAI/bge-reranker-v2-m3 (multilingual)
    - cross-encoder/ms-marco-MiniLM-L-6-v2 (fast)
    """
    
    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        device: str = "cpu",
    ):
        self.model_name = model_name
        self.device = device
        self._model = None
    
    def _get_model(self):
        """Load cross-encoder model."""
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(
                    self.model_name,
                    device=self.device,
                )
            except ImportError:
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Run: pip install sentence-transformers"
                )
        return self._model
    
    async def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_n: int = settings.rerank_top_n,
    ) -> List[RetrievalResult]:
        """Rerank using local cross-encoder."""
        if not results:
            return results
        
        model = self._get_model()
        
        # Prepare pairs
        pairs = [(query, r.text) for r in results]
        
        # Score
        scores = model.predict(pairs)
        
        # Sort by score
        scored_results = list(zip(results, scores))
        scored_results.sort(key=lambda x: x[1], reverse=True)
        
        # Return top N with updated scores
        reranked = []
        for result, score in scored_results[:top_n]:
            reranked.append(RetrievalResult(
                node_id=result.node_id,
                text=result.text,
                score=float(score),
                metadata=result.metadata,
                parent_text=result.parent_text,
            ))
        
        return reranked


class NoOpReranker(Reranker):
    """No-op reranker that just truncates results."""
    
    async def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_n: int = settings.rerank_top_n,
    ) -> List[RetrievalResult]:
        """Return top N results without reranking."""
        return results[:top_n]


def get_reranker(reranker_type: str = "cohere") -> Reranker:
    """
    Factory function to get a reranker.
    
    Args:
        reranker_type: One of "cohere", "local", "none"
        
    Returns:
        Reranker instance
    """
    if not settings.rerank_enabled:
        return NoOpReranker()
    
    rerankers = {
        "cohere": CohereReranker,
        "llamaindex_cohere": LlamaIndexCohereReranker,
        "local": LocalReranker,
        "none": NoOpReranker,
    }
    
    if reranker_type not in rerankers:
        logger.warning(f"Unknown reranker type '{reranker_type}', using 'cohere'")
        reranker_type = "cohere"
    
    return rerankers[reranker_type]()
