"""
DevChat v2.0 SOTA - Main Agent

The central orchestrator that combines all components:
- Query processing
- Hybrid retrieval
- Reranking
- Context building
- Adaptive synthesis
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Dict, List, Optional

from src.config.settings import settings
from src.generation.citations import add_citations_to_answer
from src.generation.router import ModelRouter
from src.generation.synthesizer import StreamingSynthesizer, Synthesizer, SynthesisResult
from src.retrieval.context_builder import ContextBuilder, FormattedContext
from src.retrieval.hybrid_retriever import HybridRetriever, RetrievalResult
from src.retrieval.query_processor import QueryClassification, QueryProcessor
from src.retrieval.reranker import CohereReranker, Reranker, get_reranker
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DevChatResponse:
    """Complete response from DevChat."""
    answer: str
    query_type: str
    model_used: str
    num_sources: int
    citations: List[Dict]
    
    # Timing info
    query_time_ms: float = 0.0
    retrieval_time_ms: float = 0.0
    rerank_time_ms: float = 0.0
    synthesis_time_ms: float = 0.0
    total_time_ms: float = 0.0
    
    # Debug info
    expanded_query: Optional[str] = None
    filters_applied: Optional[Dict] = None
    retrieval_count: int = 0
    reranked_count: int = 0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "answer": self.answer,
            "query_type": self.query_type,
            "model_used": self.model_used,
            "num_sources": self.num_sources,
            "citations": self.citations,
            "timing": {
                "query_ms": self.query_time_ms,
                "retrieval_ms": self.retrieval_time_ms,
                "rerank_ms": self.rerank_time_ms,
                "synthesis_ms": self.synthesis_time_ms,
                "total_ms": self.total_time_ms,
            },
        }


class DevChatAgent:
    """
    Main DevChat agent orchestrating the full RAG pipeline.
    
    Pipeline:
    1. Query Processing (classification, expansion, filter extraction)
    2. Hybrid Retrieval (dense + sparse + metadata)
    3. Reranking (cross-encoder scoring)
    4. Context Building (parent expansion, grouping)
    5. Adaptive Synthesis (model routing, generation)
    """
    
    def __init__(
        self,
        retriever: Optional[HybridRetriever] = None,
        reranker: Optional[Reranker] = None,
        query_processor: Optional[QueryProcessor] = None,
        synthesizer: Optional[Synthesizer] = None,
        context_builder: Optional[ContextBuilder] = None,
    ):
        # Initialize components
        self.retriever = retriever or HybridRetriever()
        self.reranker = reranker or get_reranker()
        self.query_processor = query_processor or QueryProcessor()
        self.synthesizer = synthesizer or Synthesizer()
        self.context_builder = context_builder or ContextBuilder()
        
        # Conversation memory (optional)
        self.conversation_history: List[Dict] = []
    
    async def chat(
        self,
        query: str,
        include_citations: bool = True,
        stream: bool = False,
    ) -> DevChatResponse:
        """
        Process a user query and generate a response.
        
        Args:
            query: User's question
            include_citations: Whether to append reference list
            stream: Whether to stream the response (not implemented yet)
            
        Returns:
            DevChatResponse with answer and metadata
        """
        import time
        
        total_start = time.time()
        
        # Step 1: Query Processing
        query_start = time.time()
        processed_query = await self.query_processor.process(query)
        query_time = (time.time() - query_start) * 1000
        
        logger.info(
            f"Query processed: type={processed_query.query_type.value}, "
            f"expanded_len={len(processed_query.expanded_query)}"
        )
        
        # Step 2: Hybrid Retrieval
        retrieval_start = time.time()
        # Apply filters if explicitly extracted from query
        active_filters = processed_query.filters if processed_query.filters.has_filters() else None
        if active_filters:
            logger.info(f"Applying filters: {active_filters}")
        
        results = await self.retriever.retrieve(
            query=processed_query.primary_query,
            top_k=settings.retrieval_top_k,
            filters=active_filters,
        )
        retrieval_time = (time.time() - retrieval_start) * 1000
        retrieval_count = len(results)
        
        logger.info(f"Retrieved {retrieval_count} results")
        
        # Step 3: Reranking
        rerank_start = time.time()
        reranked_results = await self.reranker.rerank(
            query=processed_query.original_query,
            results=results,
            top_n=settings.rerank_top_n,
        )
        rerank_time = (time.time() - rerank_start) * 1000
        reranked_count = len(reranked_results)
        
        logger.info(f"Reranked to {reranked_count} results")
        
        # Step 4: Context Building
        context = self.context_builder.build(reranked_results)
        
        logger.info(
            f"Built context: {context.num_chunks} chunks, "
            f"{context.num_studies} studies, {len(context.text)} chars"
        )
        
        # Step 5: Synthesis
        synthesis_start = time.time()
        synthesis_result = await self.synthesizer.synthesize(
            query=processed_query,
            context=context,
        )
        synthesis_time = (time.time() - synthesis_start) * 1000
        
        # Add citations if requested
        answer = synthesis_result.answer
        if include_citations and context.citations:
            answer = add_citations_to_answer(answer, context.citations)
        
        # Calculate total time
        total_time = (time.time() - total_start) * 1000
        
        # Build response
        response = DevChatResponse(
            answer=answer,
            query_type=processed_query.query_type.value,
            model_used=synthesis_result.model_used,
            num_sources=context.num_studies,
            citations=context.citations,
            query_time_ms=query_time,
            retrieval_time_ms=retrieval_time,
            rerank_time_ms=rerank_time,
            synthesis_time_ms=synthesis_time,
            total_time_ms=total_time,
            expanded_query=processed_query.expanded_query,
            filters_applied=processed_query.filters.__dict__ if processed_query.filters.has_filters() else None,
            retrieval_count=retrieval_count,
            reranked_count=reranked_count,
        )
        
        # Update conversation history
        self.conversation_history.append({
            "role": "user",
            "content": query,
            "timestamp": datetime.now().isoformat(),
        })
        self.conversation_history.append({
            "role": "assistant",
            "content": answer,
            "timestamp": datetime.now().isoformat(),
        })
        
        logger.info(
            f"Response generated in {total_time:.0f}ms "
            f"(query:{query_time:.0f}, retrieval:{retrieval_time:.0f}, "
            f"rerank:{rerank_time:.0f}, synthesis:{synthesis_time:.0f})"
        )
        
        return response
    
    def chat_sync(
        self,
        query: str,
        include_citations: bool = True,
    ) -> DevChatResponse:
        """Synchronous chat."""
        import asyncio
        return asyncio.run(self.chat(query, include_citations))
    
    async def chat_stream(
        self,
        query: str,
    ) -> AsyncIterator[str]:
        """
        Stream the response as it's generated.
        
        Yields chunks of the answer text.
        """
        # Process query
        processed_query = await self.query_processor.process(query)
        
        # Retrieve and rerank
        results = await self.retriever.retrieve(
            query=processed_query.primary_query,
            top_k=settings.retrieval_top_k,
            filters=processed_query.filters if processed_query.filters.has_filters() else None,
        )
        
        reranked_results = await self.reranker.rerank(
            query=processed_query.original_query,
            results=results,
            top_n=settings.rerank_top_n,
        )
        
        # Build context
        context = self.context_builder.build(reranked_results)
        
        # Stream synthesis
        streaming_synth = StreamingSynthesizer()
        async for chunk in streaming_synth.synthesize_stream(processed_query, context):
            yield chunk
    
    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history = []
    
    def get_history(self) -> List[Dict]:
        """Get conversation history."""
        return self.conversation_history


class DevChatAgentFactory:
    """
    Factory for creating DevChat agents with different configurations.
    """
    
    @staticmethod
    def create_default() -> DevChatAgent:
        """Create agent with default settings."""
        return DevChatAgent()
    
    @staticmethod
    def create_fast() -> DevChatAgent:
        """Create agent optimized for speed (less accuracy)."""
        from src.retrieval.reranker import NoOpReranker
        
        return DevChatAgent(
            reranker=NoOpReranker(),
        )
    
    @staticmethod
    def create_accurate() -> DevChatAgent:
        """Create agent optimized for accuracy (slower)."""
        from src.retrieval.hybrid_retriever import HierarchicalRetriever
        
        return DevChatAgent(
            retriever=HierarchicalRetriever(
                num_studies=8,
                chunks_per_study=4,
            ),
        )
    
    @staticmethod
    def create_with_custom_collection(collection_name: str) -> DevChatAgent:
        """Create agent for a specific Qdrant collection."""
        return DevChatAgent(
            retriever=HybridRetriever(collection_name=collection_name),
        )
