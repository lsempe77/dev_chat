"""
DevChat v2.0 SOTA - Hybrid Retriever

Implements hybrid search combining:
- Dense vectors (semantic similarity)
- Sparse vectors (BM25/keyword matching)
- Metadata filtering
- Reciprocal Rank Fusion (RRF)
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient, models

from src.config.settings import settings
from src.ingestion.embeddings import EmbeddingGenerator
from src.retrieval.query_processor import ExtractedFilters, QueryClassification
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievalResult:
    """A single retrieval result."""
    node_id: str
    text: str
    score: float
    metadata: Dict[str, Any]
    
    # For parent-child retrieval
    parent_text: Optional[str] = None
    
    @property
    def study_id(self) -> Optional[str]:
        """Get study ID, falling back to doc_id or pdf_name for Modal-indexed docs."""
        return (
            self.metadata.get("study_id") or 
            self.metadata.get("doc_id") or 
            self.metadata.get("pdf_name") or
            self.metadata.get("document_id")
        )
    
    @property
    def title(self) -> Optional[str]:
        return self.metadata.get("title")
    
    @property
    def year(self) -> Optional[int]:
        return self.metadata.get("year")


class HybridRetriever:
    """
    Hybrid retrieval combining dense and sparse search.
    
    Features:
    - Dense vector search (Cohere embed-v4)
    - Sparse vector search (BM25-style)
    - Metadata filtering
    - Reciprocal Rank Fusion
    """
    
    def __init__(
        self,
        client: Optional[QdrantClient] = None,
        collection_name: str = settings.qdrant_collection_name,
        embedding_generator: Optional[EmbeddingGenerator] = None,
    ):
        if client is None:
            if settings.qdrant_api_key:
                client = QdrantClient(
                    url=settings.qdrant_url,
                    api_key=settings.qdrant_api_key,
                )
            else:
                client = QdrantClient(url=settings.qdrant_url)
        
        self.client = client
        self.collection_name = collection_name
        self.embedding_generator = embedding_generator or EmbeddingGenerator()
    
    async def retrieve(
        self,
        query: str,
        top_k: int = settings.retrieval_top_k,
        filters: Optional[ExtractedFilters] = None,
        alpha: float = settings.hybrid_alpha,
    ) -> List[RetrievalResult]:
        """
        Perform hybrid retrieval.
        
        Args:
            query: Search query
            top_k: Number of results to return
            filters: Metadata filters
            alpha: Weight for dense vs sparse (1.0 = pure dense)
            
        Returns:
            List of retrieval results
        """
        # Generate query embedding
        query_embedding = self.embedding_generator.embed_query(query)
        
        # Build Qdrant filter
        qdrant_filter = filters.to_qdrant_filter() if filters else None
        
        # Perform hybrid search
        if settings.hybrid_enabled and alpha < 1.0:
            results = await self._hybrid_search(
                query=query,
                query_embedding=query_embedding,
                top_k=top_k,
                qdrant_filter=qdrant_filter,
                alpha=alpha,
            )
        else:
            results = await self._dense_search(
                query_embedding=query_embedding,
                top_k=top_k,
                qdrant_filter=qdrant_filter,
            )
        
        logger.info(f"Retrieved {len(results)} results for query: '{query[:50]}...'")
        return results
    
    async def _dense_search(
        self,
        query_embedding: List[float],
        top_k: int,
        qdrant_filter: Optional[models.Filter] = None,
    ) -> List[RetrievalResult]:
        """Perform dense-only vector search."""
        search_results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            using="dense",
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        )
        
        return self._convert_query_results(search_results)
    
    async def _hybrid_search(
        self,
        query: str,
        query_embedding: List[float],
        top_k: int,
        qdrant_filter: Optional[models.Filter] = None,
        alpha: float = 0.7,
    ) -> List[RetrievalResult]:
        """
        Perform hybrid search with RRF fusion.
        
        Args:
            query: Text query for sparse search
            query_embedding: Dense embedding
            top_k: Number of results
            qdrant_filter: Metadata filter
            alpha: Dense weight (sparse weight = 1 - alpha)
        """
        # Generate sparse vector from query
        sparse_vector = self._generate_sparse_query_vector(query)
        
        # Use Qdrant's built-in hybrid search via prefetch
        search_results = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                # Dense search
                models.Prefetch(
                    query=query_embedding,
                    using="dense",
                    limit=top_k * 2,
                    filter=qdrant_filter,
                ),
                # Sparse search
                models.Prefetch(
                    query=sparse_vector,
                    using="sparse",
                    limit=top_k * 2,
                    filter=qdrant_filter,
                ),
            ],
            query=models.FusionQuery(
                fusion=models.Fusion.RRF,  # Reciprocal Rank Fusion
            ),
            limit=top_k,
            with_payload=True,
        )
        
        return self._convert_query_results(search_results)
    
    def _generate_sparse_query_vector(self, query: str) -> models.SparseVector:
        """Generate sparse vector for query using deterministic hashing."""
        import hashlib
        import re
        from collections import Counter
        
        # Tokenize
        tokens = re.findall(r'\b\w+\b', query.lower())
        
        # Filter stopwords (same list as indexer for consistency)
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'this',
            'that', 'these', 'those', 'it', 'its', 'as', 'if', 'then', 'than',
            'what', 'how', 'why', 'when', 'where', 'which', 'who',
        }
        tokens = [t for t in tokens if len(t) > 2 and t not in stopwords]
        
        # Count and convert using deterministic hash (same as indexer)
        freq = Counter(tokens)
        indices = []
        values = []
        
        for token, count in freq.items():
            # Deterministic hash: MD5 -> int -> modulo (must match indexer!)
            hash_bytes = hashlib.md5(token.encode()).digest()
            idx = int.from_bytes(hash_bytes[:4], 'big') % 100000
            indices.append(idx)
            values.append(float(count))
        
        return models.SparseVector(indices=indices, values=values)
    
    def _convert_results(self, results: List) -> List[RetrievalResult]:
        """Convert Qdrant search results to RetrievalResult objects."""
        return [
            RetrievalResult(
                node_id=str(r.id),
                text=r.payload.get("text", ""),
                score=r.score,
                metadata={k: v for k, v in r.payload.items() if k != "text"},
                parent_text=r.payload.get("parent_text_full"),
            )
            for r in results
        ]
    
    def _convert_query_results(self, response) -> List[RetrievalResult]:
        """Convert Qdrant query points results."""
        # Handle QueryResponse object from query_points
        points = response.points if hasattr(response, 'points') else response
        return [
            RetrievalResult(
                node_id=str(p.id),
                text=p.payload.get("text", "") if p.payload else "",
                score=p.score if hasattr(p, 'score') else 0.0,
                metadata={k: v for k, v in (p.payload or {}).items() if k != "text"},
                parent_text=p.payload.get("parent_text_full") if p.payload else None,
            )
            for p in points
        ]
    
    def retrieve_sync(
        self,
        query: str,
        top_k: int = settings.retrieval_top_k,
        filters: Optional[ExtractedFilters] = None,
    ) -> List[RetrievalResult]:
        """Synchronous retrieval."""
        import asyncio
        return asyncio.run(self.retrieve(query, top_k, filters))


class HierarchicalRetriever(HybridRetriever):
    """
    Hierarchical retrieval with study-level grouping.
    
    1. Retrieve broadly (top 50-100 chunks)
    2. Group by study
    3. Select top N studies
    4. Return top M chunks per study
    """
    
    def __init__(
        self,
        num_studies: int = 6,
        chunks_per_study: int = 3,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.num_studies = num_studies
        self.chunks_per_study = chunks_per_study
    
    async def retrieve(
        self,
        query: str,
        top_k: int = None,
        filters: Optional[ExtractedFilters] = None,
        alpha: float = settings.hybrid_alpha,
    ) -> List[RetrievalResult]:
        """Hierarchical retrieval with study grouping."""
        # Get broad initial set
        broad_results = await super().retrieve(
            query=query,
            top_k=settings.retrieval_top_k,  # Get more initially
            filters=filters,
            alpha=alpha,
        )
        
        # Group by study
        by_study: Dict[str, List[RetrievalResult]] = {}
        for result in broad_results:
            study_id = result.study_id or "unknown"
            if study_id not in by_study:
                by_study[study_id] = []
            by_study[study_id].append(result)
        
        # Rank studies by best chunk score
        ranked_studies = sorted(
            by_study.items(),
            key=lambda kv: max(r.score for r in kv[1]),
            reverse=True,
        )
        
        # Select top studies and chunks
        selected = []
        for study_id, chunks in ranked_studies[:self.num_studies]:
            # Sort chunks by score
            sorted_chunks = sorted(chunks, key=lambda r: r.score, reverse=True)
            selected.extend(sorted_chunks[:self.chunks_per_study])
        
        logger.info(
            f"Hierarchical retrieval: {len(by_study)} studies → "
            f"{min(len(by_study), self.num_studies)} studies, "
            f"{len(selected)} chunks"
        )
        
        return selected
