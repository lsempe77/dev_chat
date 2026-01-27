"""
DevChat v2.0 SOTA - Hybrid Retriever

Implements hybrid search combining:
- Dense vectors (semantic similarity)
- Sparse vectors (BM25/keyword matching)
- Metadata filtering
- Reciprocal Rank Fusion (RRF)
- MMR diversity filtering
- Multi-Query RAG-Fusion (query variants with RRF)
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import numpy as np

from qdrant_client import QdrantClient, models

from src.config.settings import settings
from src.ingestion.embeddings import EmbeddingGenerator
from src.retrieval.query_processor import ExtractedFilters, QueryClassification
from src.utils.logging import get_logger

logger = get_logger(__name__)


def mmr_diversity_filter(
    results: List["RetrievalResult"],
    query_embedding: List[float],
    embeddings: List[List[float]],
    lambda_param: float = 0.7,
    top_k: Optional[int] = None,
) -> List["RetrievalResult"]:
    """
    Apply Maximal Marginal Relevance (MMR) to diversify results.
    
    MMR balances relevance to query with diversity from already-selected items.
    This reduces redundant chunks that say similar things.
    
    MMR score = lambda * similarity(doc, query) - (1-lambda) * max(similarity(doc, selected))
    
    Args:
        results: Retrieved results sorted by relevance
        query_embedding: Query embedding vector
        embeddings: Embedding vectors for each result (same order as results)
        lambda_param: Balance between relevance (1.0) and diversity (0.0). Default 0.7
        top_k: Number of results to return (default: all)
        
    Returns:
        Reordered results with more diversity
        
    Reference: "The Use of MMR, Diversity-Based Reranking..." (Carbonell & Goldstein, 1998)
    """
    if len(results) <= 1 or len(embeddings) != len(results):
        return results
    
    top_k = top_k or len(results)
    
    # Convert to numpy for efficiency
    query_vec = np.array(query_embedding)
    doc_vecs = np.array(embeddings)
    
    # Normalize vectors for cosine similarity
    query_vec = query_vec / (np.linalg.norm(query_vec) + 1e-9)
    doc_norms = np.linalg.norm(doc_vecs, axis=1, keepdims=True) + 1e-9
    doc_vecs = doc_vecs / doc_norms
    
    # Compute query-document similarities
    query_sims = doc_vecs @ query_vec
    
    # Compute document-document similarities (for diversity penalty)
    doc_doc_sims = doc_vecs @ doc_vecs.T
    
    # Greedy MMR selection
    selected_indices = []
    remaining = set(range(len(results)))
    
    # First: select highest relevance
    first_idx = int(np.argmax(query_sims))
    selected_indices.append(first_idx)
    remaining.remove(first_idx)
    
    # Iteratively select based on MMR score
    while len(selected_indices) < top_k and remaining:
        best_score = -float('inf')
        best_idx = None
        
        for idx in remaining:
            # Relevance to query
            relevance = query_sims[idx]
            
            # Max similarity to already selected (diversity penalty)
            max_sim_to_selected = max(doc_doc_sims[idx, s] for s in selected_indices)
            
            # MMR score
            mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim_to_selected
            
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx
        
        if best_idx is not None:
            selected_indices.append(best_idx)
            remaining.remove(best_idx)
    
    # Return reordered results
    reordered = [results[i] for i in selected_indices]
    
    if len(reordered) < len(results):
        logger.debug(f"MMR diversity: {len(results)} → {len(reordered)} results (lambda={lambda_param})")
    else:
        logger.debug(f"MMR diversity reordering applied to {len(reordered)} results")
    
    return reordered


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
    - MMR diversity filtering
    """
    
    def __init__(
        self,
        client: Optional[QdrantClient] = None,
        collection_name: str = settings.qdrant_collection_name,
        embedding_generator: Optional[EmbeddingGenerator] = None,
        mmr_enabled: bool = True,
        mmr_lambda: float = 0.7,  # Balance: 1.0 = pure relevance, 0.0 = pure diversity
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
        self._has_sparse_vectors: Optional[bool] = None  # Cached check
        self._has_binary_quantization: Optional[bool] = None  # Cached check for binary quantization
        self.mmr_enabled = mmr_enabled
        self.mmr_lambda = mmr_lambda
    
    def _check_sparse_support(self) -> bool:
        """Check if the collection has sparse vector support."""
        if self._has_sparse_vectors is not None:
            return self._has_sparse_vectors
        
        try:
            collection_info = self.client.get_collection(self.collection_name)
            # Check if sparse vectors are configured
            vectors_config = collection_info.config.params.vectors
            if isinstance(vectors_config, dict):
                self._has_sparse_vectors = "sparse" in vectors_config
            else:
                self._has_sparse_vectors = False
            logger.info(f"Collection {self.collection_name} sparse support: {self._has_sparse_vectors}")
        except Exception as e:
            logger.warning(f"Could not check sparse support: {e}")
            self._has_sparse_vectors = False
        
        return self._has_sparse_vectors
    
    def _check_binary_quantization(self) -> bool:
        """Check if the collection has binary quantization enabled for fast search."""
        if self._has_binary_quantization is not None:
            return self._has_binary_quantization
        
        try:
            collection_info = self.client.get_collection(self.collection_name)
            # Binary quantization is handled automatically by Qdrant when configured
            quant_config = collection_info.config.quantization_config
            self._has_binary_quantization = quant_config is not None
            logger.info(f"Collection {self.collection_name} binary quantization: {self._has_binary_quantization}")
        except Exception as e:
            logger.warning(f"Could not check binary quantization: {e}")
            self._has_binary_quantization = False
        
        return self._has_binary_quantization
    
    async def retrieve(
        self,
        query: str,
        top_k: int = settings.retrieval_top_k,
        filters: Optional[ExtractedFilters] = None,
        alpha: float = settings.hybrid_alpha,
    ) -> List[RetrievalResult]:
        """
        Perform hybrid retrieval with optional MMR diversity filtering.
        
        Binary quantization (if enabled on collection) is handled automatically
        by Qdrant for ~32x faster search with automatic rescoring.
        
        MMR (Maximal Marginal Relevance) promotes diversity by balancing
        relevance to query against similarity to already-selected documents.
        
        Args:
            query: Search query
            top_k: Number of results to return
            filters: Metadata filters
            alpha: Weight for dense vs sparse (1.0 = pure dense)
            
        Returns:
            List of retrieval results
        """
        # Log if binary quantization is active (handled automatically by Qdrant)
        if self._check_binary_quantization():
            logger.debug("Binary quantization enabled - Qdrant handles fast candidate retrieval automatically")
        
        # Generate query embedding
        query_embedding = self.embedding_generator.embed_query(query)
        
        # Build Qdrant filter
        qdrant_filter = filters.to_qdrant_filter() if filters else None
        
        # Determine if we need to fetch extra results for MMR filtering
        # MMR needs a larger candidate pool to select diverse results from
        fetch_k = top_k * 2 if self.mmr_enabled else top_k
        
        # Perform hybrid search
        # Only use hybrid if enabled, alpha < 1, AND collection supports sparse vectors
        use_hybrid = settings.hybrid_enabled and alpha < 1.0 and self._check_sparse_support()
        
        if use_hybrid:
            results, embeddings = await self._hybrid_search(
                query=query,
                query_embedding=query_embedding,
                top_k=fetch_k,
                qdrant_filter=qdrant_filter,
                alpha=alpha,
                with_vectors=self.mmr_enabled,
            )
        else:
            results, embeddings = await self._dense_search(
                query_embedding=query_embedding,
                top_k=fetch_k,
                qdrant_filter=qdrant_filter,
                with_vectors=self.mmr_enabled,
            )
        
        # Apply MMR diversity filtering if enabled
        if self.mmr_enabled and len(results) > top_k and embeddings:
            logger.debug(f"Applying MMR diversity filter (lambda={self.mmr_lambda}) to {len(results)} candidates")
            results = mmr_diversity_filter(
                results=results,
                embeddings=embeddings,
                query_embedding=query_embedding,
                top_k=top_k,
                lambda_param=self.mmr_lambda,
            )
            logger.info(f"MMR selected {len(results)} diverse results from {fetch_k} candidates")
        elif len(results) > top_k:
            # Truncate to top_k if MMR not applied
            results = results[:top_k]
        
        logger.info(f"Retrieved {len(results)} results for query: '{query[:50]}...'")
        return results

    async def retrieve_multi_query(
        self,
        queries: List[str],
        top_k: int = settings.retrieval_top_k,
        filters: Optional[ExtractedFilters] = None,
        alpha: float = settings.hybrid_alpha,
        rrf_k: int = 60,
    ) -> List[RetrievalResult]:
        """
        Perform multi-query retrieval with Reciprocal Rank Fusion.
        
        RAG-Fusion technique: retrieve for multiple query variants and fuse
        results using RRF to capture documents that match different phrasings.
        
        Args:
            queries: List of query variants (first is typically the original)
            top_k: Number of final results to return
            filters: Metadata filters
            alpha: Weight for dense vs sparse
            rrf_k: RRF ranking constant (higher = more weight to lower ranks)
            
        Returns:
            Fused results from all queries
            
        Reference: RAG-Fusion paper (https://arxiv.org/abs/2402.03367)
        """
        import asyncio
        
        if len(queries) == 1:
            # Single query - use standard retrieval
            return await self.retrieve(queries[0], top_k, filters, alpha)
        
        logger.info(f"Multi-query retrieval with {len(queries)} variants")
        
        # Retrieve for each query variant in parallel
        # Fetch more results per query since we'll deduplicate
        per_query_k = top_k * 2
        
        retrieval_tasks = [
            self.retrieve(q, per_query_k, filters, alpha)
            for q in queries
        ]
        
        all_results = await asyncio.gather(*retrieval_tasks)
        
        # Apply Reciprocal Rank Fusion
        fused_results = self._reciprocal_rank_fusion(
            all_results,
            k=rrf_k,
            top_k=top_k,
        )
        
        logger.info(
            f"RRF fused {sum(len(r) for r in all_results)} results from "
            f"{len(queries)} queries into {len(fused_results)} final results"
        )
        
        return fused_results

    async def retrieve_with_decomposition(
        self,
        query: str,
        sub_queries: List[str],
        top_k: int = settings.retrieval_top_k,
        filters: Optional[ExtractedFilters] = None,
        alpha: float = settings.hybrid_alpha,
    ) -> List[RetrievalResult]:
        """
        Retrieve using query decomposition.
        
        For complex queries that have been decomposed, retrieves for each
        sub-query and merges results using RRF. This improves recall for
        comparisons and multi-aspect questions.
        
        Args:
            query: Original query (for fallback/context)
            sub_queries: Decomposed sub-queries
            top_k: Number of final results
            filters: Metadata filters
            alpha: Dense/sparse weight
            
        Returns:
            Merged results from all sub-queries
        """
        if not sub_queries:
            # No decomposition - use standard retrieval
            return await self.retrieve(query, top_k, filters, alpha)
        
        logger.info(f"Query decomposition retrieval with {len(sub_queries)} sub-queries")
        
        # Retrieve for each sub-query
        all_queries = sub_queries + [query]  # Include original as fallback
        
        return await self.retrieve_multi_query(
            queries=all_queries,
            top_k=top_k,
            filters=filters,
            alpha=alpha,
        )

    async def retrieve_with_step_back(
        self,
        query: str,
        step_back_query: str,
        top_k: int = settings.retrieval_top_k,
        filters: Optional[ExtractedFilters] = None,
        alpha: float = settings.hybrid_alpha,
    ) -> List[RetrievalResult]:
        """
        Retrieve using step-back prompting strategy.
        
        First retrieves for the broader step-back query to get context,
        then retrieves for the specific query. Results are merged with RRF,
        giving the specific query higher weight.
        
        Args:
            query: Original specific query
            step_back_query: Broader context query
            top_k: Number of final results
            filters: Metadata filters
            alpha: Dense/sparse weight
            
        Returns:
            Merged results prioritizing specific query matches
        """
        logger.info(f"Step-back retrieval: general='{step_back_query[:50]}...'")
        
        # Retrieve for both queries
        # Give specific query more weight by putting it first (RRF favors earlier results)
        return await self.retrieve_multi_query(
            queries=[query, step_back_query],
            top_k=top_k,
            filters=filters,
            alpha=alpha,
        )

    def _reciprocal_rank_fusion(
        self,
        result_lists: List[List[RetrievalResult]],
        k: int = 60,
        top_k: int = 10,
    ) -> List[RetrievalResult]:
        """
        Fuse multiple result lists using Reciprocal Rank Fusion.
        
        RRF score = sum(1 / (k + rank)) for each list where document appears.
        
        Args:
            result_lists: List of result lists from different queries
            k: RRF constant (default 60, from original paper)
            top_k: Number of results to return
            
        Returns:
            Fused and deduplicated results
        """
        # Track scores and keep first occurrence of each document
        doc_scores: Dict[str, float] = {}
        doc_results: Dict[str, RetrievalResult] = {}
        
        for results in result_lists:
            for rank, result in enumerate(results):
                doc_id = result.node_id
                
                # RRF formula: 1 / (k + rank)
                # rank is 0-indexed, so rank 0 gets 1/(k+0) = 1/k
                rrf_score = 1.0 / (k + rank)
                
                doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + rrf_score
                
                # Keep first occurrence (typically highest score from individual query)
                if doc_id not in doc_results:
                    doc_results[doc_id] = result
        
        # Sort by RRF score descending
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Build final result list with RRF scores
        fused = []
        for doc_id, rrf_score in sorted_docs[:top_k]:
            result = doc_results[doc_id]
            # Update score to RRF score for transparency
            result.score = rrf_score
            fused.append(result)
        
        return fused
    
    async def _dense_search(
        self,
        query_embedding: List[float],
        top_k: int,
        qdrant_filter: Optional[models.Filter] = None,
        with_vectors: bool = False,
    ) -> tuple[List[RetrievalResult], Optional[List[List[float]]]]:
        """
        Perform dense-only vector search.
        
        Binary quantization (if enabled) is handled automatically by Qdrant
        for fast candidate retrieval with automatic rescoring.
        
        Args:
            query_embedding: Dense query vector
            top_k: Number of results
            qdrant_filter: Metadata filter
            with_vectors: Whether to return document vectors (for MMR)
            
        Returns:
            Tuple of (results, embeddings). Embeddings is None if with_vectors=False.
        """
        search_results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            using="dense",
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
            with_vectors=with_vectors,
        )
        
        results = self._convert_query_results(search_results)
        
        # Extract embeddings if requested
        embeddings = None
        if with_vectors:
            points = search_results.points if hasattr(search_results, 'points') else search_results
            embeddings = []
            for p in points:
                if hasattr(p, 'vector') and p.vector:
                    # Handle both direct vector and named vectors
                    if isinstance(p.vector, dict):
                        # Named vectors - get 'dense' vector
                        embeddings.append(p.vector.get('dense', []))
                    else:
                        embeddings.append(list(p.vector))
                else:
                    embeddings.append([])
        
        return results, embeddings
    
    async def _hybrid_search(
        self,
        query: str,
        query_embedding: List[float],
        top_k: int,
        qdrant_filter: Optional[models.Filter] = None,
        alpha: float = 0.7,
        with_vectors: bool = False,
    ) -> tuple[List[RetrievalResult], Optional[List[List[float]]]]:
        """
        Perform hybrid search with RRF fusion.
        
        Binary quantization (if enabled) is handled automatically by Qdrant.
        
        Args:
            query: Text query for sparse search
            query_embedding: Dense embedding
            top_k: Number of results
            qdrant_filter: Metadata filter
            alpha: Dense weight (sparse weight = 1 - alpha)
            with_vectors: Whether to return document vectors (for MMR)
            
        Returns:
            Tuple of (results, embeddings). Embeddings is None if with_vectors=False.
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
            with_vectors=with_vectors,
        )
        
        results = self._convert_query_results(search_results)
        
        # Extract embeddings if requested
        embeddings = None
        if with_vectors:
            points = search_results.points if hasattr(search_results, 'points') else search_results
            embeddings = []
            for p in points:
                if hasattr(p, 'vector') and p.vector:
                    # Handle both direct vector and named vectors
                    if isinstance(p.vector, dict):
                        # Named vectors - get 'dense' vector
                        embeddings.append(p.vector.get('dense', []))
                    else:
                        embeddings.append(list(p.vector))
                else:
                    embeddings.append([])
        
        return results, embeddings
    
    def _generate_sparse_query_vector(self, query: str) -> models.SparseVector:
        """Generate sparse vector for query using deterministic hashing."""
        import hashlib
        import re
        from collections import Counter, defaultdict
        
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
        
        # Aggregate by index to handle hash collisions (REQUIRED for Qdrant)
        index_weights = defaultdict(float)
        
        for token, count in freq.items():
            # Deterministic hash: MD5 -> int -> modulo (must match indexer!)
            hash_bytes = hashlib.md5(token.encode()).digest()
            idx = int.from_bytes(hash_bytes[:4], 'big') % 100000
            index_weights[idx] += float(count)
        
        # Convert to sorted lists (Qdrant requires unique indices)
        sorted_items = sorted(index_weights.items())
        indices = [idx for idx, _ in sorted_items]
        values = [val for _, val in sorted_items]
        
        return models.SparseVector(indices=indices, values=values)
    
    def _convert_results(self, results: List) -> List[RetrievalResult]:
        """Convert Qdrant search results to RetrievalResult objects."""
        converted = []
        for r in results:
            # Ensure text is always a string (handle legacy list format)
            raw_text = r.payload.get("text", "")
            if isinstance(raw_text, list):
                text = " ".join(str(t) for t in raw_text)
            else:
                text = str(raw_text) if raw_text else ""
            
            # Handle parent_text for parent-child chunking
            # Try new field name first, fall back to legacy
            raw_parent = r.payload.get("parent_text") or r.payload.get("parent_text_full")
            if isinstance(raw_parent, list):
                parent_text = " ".join(str(t) for t in raw_parent)
            else:
                parent_text = str(raw_parent) if raw_parent else None
            
            converted.append(RetrievalResult(
                node_id=str(r.id),
                text=text,
                score=r.score,
                metadata={k: v for k, v in r.payload.items() if k != "text"},
                parent_text=parent_text,
            ))
        return converted
    
    def _convert_query_results(self, response) -> List[RetrievalResult]:
        """Convert Qdrant query points results."""
        # Handle QueryResponse object from query_points
        points = response.points if hasattr(response, 'points') else response
        converted = []
        for p in points:
            # Ensure text is always a string (handle legacy list format)
            raw_text = p.payload.get("text", "") if p.payload else ""
            if isinstance(raw_text, list):
                text = " ".join(str(t) for t in raw_text)
            else:
                text = str(raw_text) if raw_text else ""
            
            # Handle parent_text for parent-child chunking
            raw_parent = p.payload.get("parent_text") or p.payload.get("parent_text_full") if p.payload else None
            if isinstance(raw_parent, list):
                parent_text = " ".join(str(t) for t in raw_parent)
            else:
                parent_text = str(raw_parent) if raw_parent else None
            
            converted.append(RetrievalResult(
                node_id=str(p.id),
                text=text,
                score=p.score if hasattr(p, 'score') else 0.0,
                metadata={k: v for k, v in (p.payload or {}).items() if k != "text"},
                parent_text=parent_text,
            ))
        return converted
    
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
