"""
DevChat v2.0 SOTA - Graph-Enhanced Retrieval

Combines vector search with knowledge graph for richer retrieval.

Strategy:
1. Run vector search (dense + sparse hybrid)
2. Run graph search in parallel
3. Merge and deduplicate results
4. Boost scores for graph-connected documents
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.config.settings import settings
from src.database.knowledge_graph import get_knowledge_graph_service
from src.retrieval.hybrid_retriever import HybridRetriever, RetrievalResult
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GraphEnhancedResult(RetrievalResult):
    """Retrieval result with optional graph context."""
    graph_relations: List[str] = field(default_factory=list)
    graph_boost: float = 0.0


class GraphEnhancedRetriever:
    """
    Retriever that combines vector and graph search.
    
    For queries about relationships, conflicts, or comparisons,
    the graph provides structured navigation between studies.
    
    For factual queries, vector search is primary with graph boosting.
    """
    
    def __init__(
        self,
        vector_retriever: Optional[HybridRetriever] = None,
        graph_weight: float = 0.3,
    ):
        """
        Initialize graph-enhanced retriever.
        
        Args:
            vector_retriever: Base vector retriever
            graph_weight: Weight for graph-based scoring (0-1)
        """
        self.vector_retriever = vector_retriever or HybridRetriever()
        self.graph_weight = graph_weight
        self.graph_service = get_knowledge_graph_service()
    
    async def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters = None,
        alpha: Optional[float] = None,
        use_graph: bool = True,
    ) -> List[RetrievalResult]:
        """
        Retrieve documents using both vector and graph search.
        
        Args:
            query: Search query
            top_k: Number of results
            filters: Metadata filters
            alpha: Dense/sparse weight
            use_graph: Whether to use graph search
            
        Returns:
            List of retrieval results
        """
        top_k = top_k or settings.retrieval_top_k
        
        # Prepare vector search kwargs
        vector_kwargs = {"query": query, "top_k": top_k}
        if filters:
            vector_kwargs["filters"] = filters
        if alpha:
            vector_kwargs["alpha"] = alpha
        
        # Run searches in parallel
        if use_graph and settings.knowledge_graph_enabled:
            vector_task = self.vector_retriever.retrieve(**vector_kwargs)
            graph_task = self._graph_search(query, limit=top_k // 2)
            
            vector_results, graph_results = await asyncio.gather(
                vector_task,
                graph_task,
                return_exceptions=True,
            )
            
            # Handle exceptions
            if isinstance(vector_results, Exception):
                logger.error(f"Vector search failed: {vector_results}")
                vector_results = []
            if isinstance(graph_results, Exception):
                logger.warning(f"Graph search failed: {graph_results}")
                graph_results = []
            
            # Merge results
            return self._merge_results(vector_results, graph_results, top_k)
        else:
            # Vector-only search
            return await self.vector_retriever.retrieve(**vector_kwargs)
    
    async def _graph_search(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search knowledge graph for related studies.
        
        Args:
            query: Search query
            limit: Max results
            
        Returns:
            List of graph results
        """
        try:
            return await self.graph_service.search_related_studies(query, limit)
        except Exception as e:
            logger.warning(f"Graph search failed: {e}")
            return []
    
    def _merge_results(
        self,
        vector_results: List[RetrievalResult],
        graph_results: List[Dict[str, Any]],
        top_k: int,
    ) -> List[RetrievalResult]:
        """
        Merge vector and graph results.
        
        Strategy:
        - Keep all vector results
        - Boost scores for documents also found via graph
        - Add graph-only results at the end with adjusted scores
        
        Args:
            vector_results: Results from vector search
            graph_results: Results from graph search
            top_k: Final result count
            
        Returns:
            Merged and scored results
        """
        # Create lookup for graph results
        graph_study_ids = {r.get("study_id"): r for r in graph_results}
        
        merged = []
        seen_ids = set()
        
        # Process vector results and boost if also in graph
        for result in vector_results:
            study_id = result.study_id
            
            if study_id in graph_study_ids:
                # Boost score for graph match
                graph_info = graph_study_ids[study_id]
                boosted_score = result.score + (self.graph_weight * 0.5)
                
                # Create enhanced result
                enhanced = GraphEnhancedResult(
                    node_id=result.node_id,
                    text=result.text,
                    score=min(boosted_score, 1.0),  # Cap at 1.0
                    metadata=result.metadata,
                    parent_text=result.parent_text,
                    graph_relations=[
                        f"{graph_info.get('relation', 'RELATED_TO')} {graph_info.get('related_entity', '')}"
                    ],
                    graph_boost=self.graph_weight * 0.5,
                )
                merged.append(enhanced)
                logger.debug(f"Graph-boosted: {study_id} ({result.score:.3f} -> {enhanced.score:.3f})")
            else:
                merged.append(result)
            
            seen_ids.add(study_id)
        
        # Add graph-only results (not found in vector search)
        for study_id, graph_info in graph_study_ids.items():
            if study_id not in seen_ids and len(merged) < top_k * 2:
                # Create placeholder result from graph
                # These will need to be enriched with actual chunks later
                graph_only = GraphEnhancedResult(
                    node_id=f"graph_{study_id}",
                    text=f"[Graph result: {graph_info.get('title', study_id)}]",
                    score=self.graph_weight * 0.3,  # Lower score for graph-only
                    metadata={
                        "study_id": study_id,
                        "title": graph_info.get("title"),
                        "year": graph_info.get("year"),
                        "source": "knowledge_graph",
                    },
                    graph_relations=[
                        f"{graph_info.get('relation', 'RELATED_TO')} {graph_info.get('related_entity', '')}"
                    ],
                    graph_boost=self.graph_weight * 0.3,
                )
                merged.append(graph_only)
                logger.debug(f"Added graph-only result: {study_id}")
        
        # Sort by score and limit
        merged.sort(key=lambda x: x.score, reverse=True)
        
        logger.info(
            f"Merged {len(vector_results)} vector + {len(graph_results)} graph results "
            f"-> {len(merged[:top_k])} final"
        )
        
        return merged[:top_k]
    
    async def get_study_context(
        self,
        study_id: str,
    ) -> Dict[str, Any]:
        """
        Get rich context for a study from the knowledge graph.
        
        Args:
            study_id: Study identifier
            
        Returns:
            Context including related entities and studies
        """
        if not settings.knowledge_graph_enabled:
            return {}
        
        try:
            # Get network and relationships in parallel
            network_task = self.graph_service.get_study_network(study_id, depth=2)
            contradictions_task = self.graph_service.find_contradicting_studies(study_id)
            supporting_task = self.graph_service.find_supporting_studies(study_id)
            
            network, contradictions, supporting = await asyncio.gather(
                network_task,
                contradictions_task,
                supporting_task,
                return_exceptions=True,
            )
            
            return {
                "network": network if not isinstance(network, Exception) else {},
                "contradicting_studies": contradictions if not isinstance(contradictions, Exception) else [],
                "supporting_studies": supporting if not isinstance(supporting, Exception) else [],
            }
            
        except Exception as e:
            logger.warning(f"Failed to get study context: {e}")
            return {}


def get_graph_enhanced_retriever() -> GraphEnhancedRetriever:
    """Get or create a graph-enhanced retriever."""
    return GraphEnhancedRetriever()
