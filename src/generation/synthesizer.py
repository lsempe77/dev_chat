"""
DevChat v2.0 SOTA - Answer Synthesizer

Generate high-quality answers from retrieved context:
- Structured synthesis for complex queries
- Citation integration
- Conflict resolution for contradictory findings
"""

from dataclasses import dataclass
from typing import List, Optional

from src.config.prompts import get_synthesis_prompt, get_system_prompt
from src.config.settings import settings
from src.generation.router import ModelRouter, RoutingDecision
from src.retrieval.context_builder import FormattedContext
from src.retrieval.query_processor import QueryClassification, QueryType
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SynthesisResult:
    """Result of answer synthesis."""
    answer: str
    query_type: str
    model_used: str
    num_sources: int
    citations: List[dict]
    
    # Metadata
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class Synthesizer:
    """
    Synthesize answers from retrieved context.
    
    Uses adaptive model routing based on query complexity.
    """
    
    def __init__(self, router: Optional[ModelRouter] = None):
        self.router = router or ModelRouter()
    
    async def synthesize(
        self,
        query: QueryClassification,
        context: FormattedContext,
    ) -> SynthesisResult:
        """
        Generate an answer from query and context.
        
        Args:
            query: Processed query with classification
            context: Formatted context from retrieval
            
        Returns:
            SynthesisResult with answer and metadata
        """
        # Route to appropriate model
        routing = self.router.route(
            query_type=query.query_type,
            context_length=len(context.text),
            num_studies=context.num_studies,
        )
        
        logger.info(
            f"Routing to {routing.tier.value} model: {routing.model_name} "
            f"({routing.reason})"
        )
        
        # Get LLM
        llm = self.router.get_llm(routing)
        
        # Build prompts - pass num_studies for proper framing
        system_prompt = get_system_prompt(query.query_type.value)
        synthesis_prompt = get_synthesis_prompt(
            query=query.original_query,
            context=context.text,
            query_type=query.query_type.value,
            num_studies=context.num_studies,
        )
        
        # Generate response
        try:
            # Build full prompt with system context
            full_prompt = f"{system_prompt}\n\n{synthesis_prompt}"
            
            response = await llm.acomplete(full_prompt)
            
            answer = response.text
            
            # Extract token counts if available
            input_tokens = getattr(response, 'prompt_tokens', None)
            output_tokens = getattr(response, 'completion_tokens', None)
            
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            answer = (
                "I encountered an error while generating the response. "
                "Please try again or rephrase your question."
            )
            input_tokens = None
            output_tokens = None
        
        return SynthesisResult(
            answer=answer,
            query_type=query.query_type.value,
            model_used=routing.model_name,
            num_sources=context.num_studies,
            citations=context.citations,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    
    def synthesize_sync(
        self,
        query: QueryClassification,
        context: FormattedContext,
    ) -> SynthesisResult:
        """Synchronous synthesis."""
        import asyncio
        return asyncio.run(self.synthesize(query, context))


class StreamingSynthesizer(Synthesizer):
    """
    Synthesizer with streaming output support.
    
    Yields chunks of the response as they're generated.
    """
    
    async def synthesize_stream(
        self,
        query: QueryClassification,
        context: FormattedContext,
    ):
        """
        Generate answer with streaming.
        
        Yields:
            Chunks of the response text
        """
        # Route to appropriate model
        routing = self.router.route(
            query_type=query.query_type,
            context_length=len(context.text),
            num_studies=context.num_studies,
        )
        
        llm = self.router.get_llm(routing)
        
        # Build prompts
        system_prompt = get_system_prompt(query.query_type.value)
        synthesis_prompt = get_synthesis_prompt(
            query=query.original_query,
            context=context.text,
            query_type=query.query_type.value,
        )
        
        # Stream response
        try:
            response_gen = await llm.astream_complete(
                synthesis_prompt,
                system_prompt=system_prompt,
            )
            
            async for chunk in response_gen:
                yield chunk.delta
                
        except Exception as e:
            logger.error(f"Streaming synthesis failed: {e}")
            yield "Error generating response. Please try again."


class MultiDocumentSynthesizer:
    """
    Specialized synthesizer for multi-document analysis.
    
    Handles:
    - Cross-study comparisons
    - Conflict resolution
    - Evidence synthesis
    """
    
    def __init__(self):
        self.router = ModelRouter()
    
    async def compare_studies(
        self,
        query: str,
        context: FormattedContext,
    ) -> SynthesisResult:
        """
        Generate a comparison across multiple studies.
        
        Explicitly identifies agreements, disagreements, and explanations.
        """
        from src.config.prompts import COMPARISON_PROMPT
        
        # Always use reasoning model for comparisons
        routing = self.router.route(
            query_type=QueryType.COMPARISON,
            num_studies=context.num_studies,
        )
        
        llm = self.router.get_llm(routing)
        
        prompt = COMPARISON_PROMPT.format(
            query=query,
            context=context.text,
        )
        
        response = await llm.acomplete(prompt)
        
        return SynthesisResult(
            answer=response.text,
            query_type="comparison",
            model_used=routing.model_name,
            num_sources=context.num_studies,
            citations=context.citations,
        )
    
    async def synthesize_with_conflicts(
        self,
        query: str,
        context: FormattedContext,
    ) -> SynthesisResult:
        """
        Synthesize findings while explicitly addressing conflicts.
        
        Uses a two-stage approach:
        1. Identify key claims and their sources
        2. Synthesize with conflict annotation
        """
        # Stage 1: Extract claims
        claim_extraction_prompt = f"""
        From the following research context, identify the key claims/findings.
        For each claim, note:
        1. The claim itself
        2. Which study/studies support it
        3. Any conflicting evidence
        
        Context:
        {context.text}
        
        Extract claims in this format:
        - Claim: [claim]
          Support: [study names/years]
          Conflicts: [any contradicting evidence]
        """
        
        # For now, use single-stage synthesis
        # TODO: Implement two-stage extraction
        return await self.compare_studies(query, context)
