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
from typing import AsyncIterator, Dict, List, Optional, Any

from src.config.settings import settings
from src.generation.citations import add_citations_to_answer, ensure_citation_coverage
from src.generation.router import ModelRouter
from src.generation.synthesizer import StreamingSynthesizer, Synthesizer, SynthesisResult
from src.retrieval.context_builder import ContextBuilder, FormattedContext
from src.retrieval.hybrid_retriever import HybridRetriever, RetrievalResult
from src.retrieval.query_processor import QueryClassification, QueryProcessor
from src.retrieval.reranker import CohereReranker, Reranker, get_reranker
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SearchSettings:
    """Settings passed from frontend to control search behavior."""
    relevance_threshold: float = 0.5  # Default threshold - user can adjust
    max_studies: int = 10
    answer_style: str = "executive"
    use_reranking: bool = True
    min_confidence: str = "all"
    year_cutoff: int = 2010
    
    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "SearchSettings":
        """Create from dictionary (API request)."""
        if not data:
            return cls()
        return cls(
            relevance_threshold=data.get("relevanceThreshold", 0.5),
            max_studies=data.get("maxStudies", 10),
            answer_style=data.get("answerStyle", "executive"),
            use_reranking=data.get("useReranking", True),
            min_confidence=data.get("minConfidence", "all"),
            year_cutoff=data.get("yearCutoff", 2010),
        )


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
        search_settings: Optional[SearchSettings] = None,
    ) -> DevChatResponse:
        """
        Process a user query and generate a response.
        
        Args:
            query: User's question
            include_citations: Whether to append reference list
            stream: Whether to stream the response (not implemented yet)
            search_settings: Optional settings from frontend (relevance, max studies, etc.)
            
        Returns:
            DevChatResponse with answer and metadata
        """
        import time
        
        # Use provided settings or defaults
        user_settings = search_settings or SearchSettings()
        
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
        
        # Use maxStudies from settings for top_k (retrieve more, then filter)
        retrieval_top_k = min(user_settings.max_studies * 3, settings.retrieval_top_k)
        
        results = await self.retriever.retrieve(
            query=processed_query.primary_query,
            top_k=retrieval_top_k,
            filters=active_filters,
        )
        retrieval_time = (time.time() - retrieval_start) * 1000
        retrieval_count = len(results)
        
        logger.info(f"Retrieved {retrieval_count} results (settings.maxStudies={user_settings.max_studies})")
        
        # Step 3: Reranking (optional based on settings)
        rerank_start = time.time()
        if user_settings.use_reranking and self.reranker:
            # Rerank to user's maxStudies count
            rerank_top_n = min(user_settings.max_studies, settings.rerank_top_n)
            reranked_results = await self.reranker.rerank(
                query=processed_query.original_query,
                results=results,
                top_n=rerank_top_n,
            )
            logger.info(f"Reranked to {len(reranked_results)} results")
        else:
            # Skip reranking, just take top N
            reranked_results = results[:user_settings.max_studies]
            logger.info(f"Skipped reranking (useReranking=False), took top {len(reranked_results)}")
        
        # Apply relevance threshold filter - strictly respect user's choice
        threshold_filtered_all = False
        threshold_max_score = 0.0
        
        if user_settings.relevance_threshold > 0 and reranked_results:
            original_count = len(reranked_results)
            threshold_max_score = max((r.score for r in reranked_results), default=0)
            
            filtered_results = [
                r for r in reranked_results 
                if r.score >= user_settings.relevance_threshold
            ]
            
            if filtered_results:
                reranked_results = filtered_results
                logger.info(f"Applied relevance threshold {user_settings.relevance_threshold}, kept {len(reranked_results)}/{original_count}")
            else:
                # Threshold filtered out ALL results
                logger.warning(
                    f"Relevance threshold {user_settings.relevance_threshold} filtered out all {original_count} results. "
                    f"Max score was {threshold_max_score:.3f}"
                )
                reranked_results = []
                threshold_filtered_all = True
        
        rerank_time = (time.time() - rerank_start) * 1000
        reranked_count = len(reranked_results)
        
        # Handle case where threshold filtered everything
        if threshold_filtered_all:
            total_time = (time.time() - total_start) * 1000
            threshold_pct = int(user_settings.relevance_threshold * 100)
            max_score_pct = int(threshold_max_score * 100)
            return DevChatResponse(
                answer=(
                    f"No results meet the current relevance threshold ({threshold_pct}%). "
                    f"The best matching document scored {max_score_pct}%. "
                    f"You might try lowering the inclusion threshold in Settings "
                    f"(which could produce less accurate results) or changing your query."
                ),
                query_type=processed_query.query_type.value,
                model_used="none",
                num_sources=0,
                citations=[],
                query_time_ms=query_time,
                retrieval_time_ms=retrieval_time,
                rerank_time_ms=rerank_time,
                synthesis_time_ms=0,
                total_time_ms=total_time,
                expanded_query=processed_query.expanded_query,
                filters_applied=None,
                retrieval_count=retrieval_count,
                reranked_count=0,
            )
        
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
        
        # Add citations if requested AND answer has useful content
        answer = synthesis_result.answer
        
        # Check if answer indicates no relevant information found
        no_info_indicators = [
            "does not contain",
            "no relevant",
            "no information",
            "unable to",
            "cannot find",
            "no studies found",
            "no evidence found",
            "i don't have",
            "i do not have",
        ]
        answer_lower = answer.lower()
        has_useful_content = not any(indicator in answer_lower for indicator in no_info_indicators)
        
        # Only add citations if we have useful content AND citations exist
        if include_citations and context.citations and has_useful_content:
            answer = add_citations_to_answer(answer, context.citations)
            
            # Ensure all retrieved sources are cited (coverage validator)
            # This adds brief mentions for any uncited sources
            answer = ensure_citation_coverage(answer, context.citations)
        
        # If no useful content, clear the citations to avoid showing empty references
        final_citations = context.citations if has_useful_content else []
        
        # Calculate total time
        total_time = (time.time() - total_start) * 1000
        
        # Build response
        response = DevChatResponse(
            answer=answer,
            query_type=processed_query.query_type.value,
            model_used=synthesis_result.model_used,
            num_sources=len(final_citations),
            citations=final_citations,
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
    
    async def generate_suggestions(
        self,
        query: str,
        answer: str,
        citations: List[Dict],
    ) -> List[str]:
        """
        Generate LLM-based follow-up query suggestions.
        
        Args:
            query: Original user query
            answer: Generated answer
            citations: List of citations used
            
        Returns:
            List of 3 suggestion strings
        """
        from src.config.prompts import SUGGESTION_GENERATION_PROMPT
        
        # Extract topics from citations
        topics = set()
        for c in citations[:5]:  # Use top 5
            sector = c.get("sector")
            if sector:
                if isinstance(sector, list):
                    topics.update(str(s) for s in sector)
                else:
                    topics.add(str(sector))
            country = c.get("country")
            if country:
                if isinstance(country, list):
                    topics.update(str(co) for co in country)
                else:
                    topics.add(str(country))
        topics_str = ", ".join(topics) if topics else "general development"
        
        # Truncate answer for prompt
        answer_summary = answer[:500] + "..." if len(answer) > 500 else answer
        
        prompt = SUGGESTION_GENERATION_PROMPT.format(
            query=query,
            answer_summary=answer_summary,
            study_count=len(citations),
            topics=topics_str,
        )
        
        try:
            # Use fast model for suggestions
            from llama_index.llms.openai_like import OpenAILike
            
            llm = OpenAILike(
                model=settings.llm_fast_model,
                api_base=settings.openrouter_base_url,
                api_key=settings.openrouter_api_key,
                temperature=0.7,
                max_tokens=150,
            )
            
            response = await llm.acomplete(prompt)
            
            # Parse response into list of suggestions
            lines = response.text.strip().split("\n")
            suggestions = [line.strip() for line in lines if line.strip()][:3]
            
            # Ensure we have 3 suggestions
            if len(suggestions) < 3:
                # Add default fallbacks
                fallbacks = [
                    "Focus on a specific region?",
                    "Compare different intervention types?",
                    "Look at more recent studies?",
                ]
                suggestions.extend(fallbacks[:(3 - len(suggestions))])
            
            logger.info(f"Generated {len(suggestions)} suggestions")
            return suggestions[:3]
            
        except Exception as e:
            logger.error(f"Failed to generate suggestions: {e}")
            # Return default suggestions on error
            return [
                "Narrow to a specific country?",
                "Compare different methodologies?",
                "Focus on studies after 2020?",
            ]


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
