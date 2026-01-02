"""
DevChat v2.0 SOTA - HyDE Query Enhancement

Hypothetical Document Embeddings (HyDE) for improved retrieval.

The idea: Instead of embedding the query directly, we:
1. Generate a hypothetical answer/document that would answer the query
2. Embed that hypothetical document
3. Use that embedding for retrieval

This bridges the gap between query-style text and document-style text,
significantly improving retrieval quality.

Reference: Gao et al. 2022 - "Precise Zero-Shot Dense Retrieval without Relevance Labels"
"""

from dataclasses import dataclass
from typing import Optional, List

from src.config.settings import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class HyDEResult:
    """Result of HyDE query enhancement."""
    original_query: str
    hypothetical_document: str
    enhanced_query: str  # For display/logging
    hyde_used: bool = True


# Domain-specific prompt for impact evaluation context
HYDE_SYSTEM_PROMPT = """You are an expert in impact evaluation research. 
Your task is to generate a hypothetical document excerpt that would perfectly answer the given research question.

Write as if you are excerpting from an actual academic paper or impact evaluation report. Include:
- Specific methodology mentions (RCT, quasi-experimental, etc.)
- Quantitative findings with effect sizes where appropriate
- Geographic and sectoral context
- Study limitations or conditions

Keep the response focused and concise (2-3 paragraphs max)."""

HYDE_USER_PROMPT = """Research Question: {query}

Generate a hypothetical excerpt from an impact evaluation study that would answer this question. 
Write in academic style as if from an actual published study."""


class HyDEEnhancer:
    """
    HyDE (Hypothetical Document Embeddings) query enhancement.
    
    Generates a hypothetical answer document to improve retrieval,
    especially for complex research questions.
    """
    
    def __init__(self, llm=None):
        """Initialize HyDE enhancer."""
        self._llm = llm
        
    def _get_llm(self):
        """Get or create LLM instance."""
        if self._llm is None:
            from llama_index.llms.openai_like import OpenAILike
            self._llm = OpenAILike(
                model=settings.llm_fast_model,  # Use fast model for efficiency
                api_key=settings.openrouter_api_key,
                api_base=settings.openrouter_base_url,
                temperature=0.7,  # Slightly creative for hypothetical generation
                max_tokens=512,  # Keep hypothetical docs concise
                is_chat_model=True,
            )
        return self._llm
    
    async def enhance(self, query: str) -> HyDEResult:
        """
        Generate a hypothetical document for the query.
        
        Args:
            query: Original user query
            
        Returns:
            HyDEResult with hypothetical document
        """
        if not settings.hyde_enabled:
            logger.debug("HyDE disabled, returning original query")
            return HyDEResult(
                original_query=query,
                hypothetical_document=query,
                enhanced_query=query,
                hyde_used=False,
            )
        
        try:
            llm = self._get_llm()
            
            # Build prompt
            prompt = f"{HYDE_SYSTEM_PROMPT}\n\n{HYDE_USER_PROMPT.format(query=query)}"
            
            response = await llm.acomplete(prompt)
            hypothetical_doc = response.text.strip()
            
            # Validate response
            if len(hypothetical_doc) < 50:
                logger.warning(f"HyDE generated short response ({len(hypothetical_doc)} chars), using original")
                return HyDEResult(
                    original_query=query,
                    hypothetical_document=query,
                    enhanced_query=query,
                    hyde_used=False,
                )
            
            logger.info(f"HyDE generated {len(hypothetical_doc)} char hypothetical document")
            
            return HyDEResult(
                original_query=query,
                hypothetical_document=hypothetical_doc,
                enhanced_query=f"[HyDE] {query[:50]}...",
                hyde_used=True,
            )
            
        except Exception as e:
            logger.warning(f"HyDE enhancement failed: {e}, using original query")
            return HyDEResult(
                original_query=query,
                hypothetical_document=query,
                enhanced_query=query,
                hyde_used=False,
            )
    
    async def enhance_multiple(self, query: str, n: int = 3) -> List[str]:
        """
        Generate multiple hypothetical documents for ensemble retrieval.
        
        Args:
            query: Original user query
            n: Number of hypothetical documents to generate
            
        Returns:
            List of hypothetical documents
        """
        import asyncio
        
        # Generate n hypothetical documents in parallel
        tasks = [self.enhance(query) for _ in range(n)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        hypotheticals = []
        for r in results:
            if isinstance(r, HyDEResult) and r.hyde_used:
                hypotheticals.append(r.hypothetical_document)
            elif not isinstance(r, Exception):
                hypotheticals.append(r.hypothetical_document if hasattr(r, 'hypothetical_document') else query)
        
        # Always include at least the original query
        if not hypotheticals:
            hypotheticals = [query]
            
        return hypotheticals


class HyDERetriever:
    """
    Wrapper that combines HyDE with any retriever.
    
    Usage:
        hyde_retriever = HyDERetriever(base_retriever)
        results = await hyde_retriever.retrieve(query)
    """
    
    def __init__(self, base_retriever, hyde_enhancer: Optional[HyDEEnhancer] = None):
        """
        Initialize HyDE retriever.
        
        Args:
            base_retriever: The underlying retriever (e.g., HybridRetriever)
            hyde_enhancer: Optional HyDE enhancer instance
        """
        self.base_retriever = base_retriever
        self.hyde = hyde_enhancer or HyDEEnhancer()
        
    async def retrieve(
        self,
        query: str,
        top_k: int = None,
        filters = None,
        alpha: float = None,
        use_hyde: bool = True,
    ):
        """
        Retrieve with optional HyDE enhancement.
        
        Args:
            query: User query
            top_k: Number of results
            filters: Metadata filters
            alpha: Dense/sparse weight
            use_hyde: Whether to use HyDE for this query
            
        Returns:
            List of retrieval results
        """
        # Prepare kwargs for base retriever
        kwargs = {}
        if top_k is not None:
            kwargs['top_k'] = top_k
        if filters is not None:
            kwargs['filters'] = filters
        if alpha is not None:
            kwargs['alpha'] = alpha
        
        if use_hyde and settings.hyde_enabled:
            # Generate hypothetical document
            hyde_result = await self.hyde.enhance(query)
            
            if hyde_result.hyde_used:
                # Use hypothetical document for retrieval
                logger.info(f"Using HyDE-enhanced query for retrieval")
                return await self.base_retriever.retrieve(
                    query=hyde_result.hypothetical_document,
                    **kwargs
                )
        
        # Fall back to regular retrieval
        return await self.base_retriever.retrieve(query=query, **kwargs)
