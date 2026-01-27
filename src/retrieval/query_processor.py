"""
DevChat v2.0 SOTA - Query Processor

Handles query understanding before retrieval:
- Query classification (simple, synthesis, comparison)
- Query expansion (synonyms, acronyms, domain terms)
- Metadata extraction (year, sector, country filters)
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from src.config.prompts import (
    METADATA_EXTRACTION_PROMPT,
    QUERY_CLASSIFICATION_PROMPT,
    QUERY_EXPANSION_PROMPT,
    QUERY_VARIANTS_PROMPT,
    QUERY_DECOMPOSITION_PROMPT,
    STEP_BACK_PROMPT,
)
from src.config.settings import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class QueryType(str, Enum):
    """Types of user queries."""
    SIMPLE = "simple"
    LOOKUP = "lookup"
    SYNTHESIS = "synthesis"
    COMPARISON = "comparison"
    METHODOLOGY = "methodology"


@dataclass
class ExtractedFilters:
    """Metadata filters extracted from query."""
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    sectors: List[str] = field(default_factory=list)
    countries: List[str] = field(default_factory=list)
    study_types: List[str] = field(default_factory=list)
    target_populations: List[str] = field(default_factory=list)
    confidence_level: Optional[str] = None

    def has_filters(self) -> bool:
        """Check if any filters are set."""
        return any([
            self.year_min,
            self.year_max,
            self.sectors,
            self.countries,
            self.study_types,
            self.target_populations,
            self.confidence_level,
        ])
    
    def to_qdrant_filter(self):
        """Convert to Qdrant filter format.
        
        Note: Only applies year filters by default since not all documents
        have country/sector metadata (e.g., Modal-indexed PDFs).
        To enable other filters, documents must have consistent metadata.
        """
        from qdrant_client.models import Filter, FieldCondition, Range, MatchAny, MatchValue
        
        conditions = []
        
        # Year filter - most documents have this
        if self.year_min or self.year_max:
            year_range = Range(
                gte=self.year_min,
                lte=self.year_max,
            )
            conditions.append(FieldCondition(key="year", range=year_range))
        
        # Sector filter (enabled now that metadata is populated)
        if self.sectors:
            conditions.append(FieldCondition(
                key="sector",
                match=MatchAny(any=self.sectors),
            ))
        
        # Target population filter
        if self.target_populations:
            conditions.append(FieldCondition(
                key="target_population",
                match=MatchAny(any=self.target_populations),
            ))

        # Enable these when the corpus is fully populated with consistent metadata
        # if self.countries:
        #     conditions.append(FieldCondition(
        #         key="country",
        #         match=MatchAny(any=self.countries),
        #     ))
        #
        # if self.study_types:
        #     conditions.append(FieldCondition(
        #         key="study_type",
        #         match=MatchAny(any=self.study_types),
        #     ))
        #
        # if self.confidence_level:
        #     conditions.append(FieldCondition(
        #         key="confidence_rating",
        #         match=MatchValue(value=self.confidence_level),
        #     ))
        
        if conditions:
            return Filter(must=conditions)
        return None


@dataclass
class QueryClassification:
    """Result of query processing."""
    original_query: str
    expanded_query: str
    query_type: QueryType
    filters: ExtractedFilters
    search_queries: List[str] = field(default_factory=list)
    sub_queries: List[str] = field(default_factory=list)  # For query decomposition
    
    @property
    def primary_query(self) -> str:
        """Get the primary query for retrieval."""
        return self.expanded_query or self.original_query
    
    @property
    def is_decomposed(self) -> bool:
        """Check if query was decomposed into sub-queries."""
        return len(self.sub_queries) > 0


class QueryProcessor:
    """
    Process user queries before retrieval.
    
    Pipeline:
    1. Classify query type
    2. Expand query with synonyms/acronyms
    3. Extract metadata filters
    """
    
    def __init__(self, llm=None):
        """
        Initialize query processor.
        
        Args:
            llm: LLM for query processing (uses fast model by default)
        """
        self._llm = llm
        
    def _get_llm(self):
        """Get or create LLM instance."""
        if self._llm is None:
            # Use OpenRouter via OpenAILike for unified API access
            from llama_index.llms.openai_like import OpenAILike
            self._llm = OpenAILike(
                model=settings.llm_fast_model,
                api_key=settings.openrouter_api_key,
                api_base=settings.openrouter_base_url,
                temperature=0.0,
                max_tokens=1024,
                is_chat_model=True,
            )
        return self._llm
    
    async def process(self, query: str) -> QueryClassification:
        """
        Process a user query.
        
        Args:
            query: Raw user query
            
        Returns:
            Classified and expanded query with filters
        """
        import asyncio
        
        # Run all processing steps IN PARALLEL (they're independent)
        query_type, expanded_query, filters = await asyncio.gather(
            self._classify_query(query),
            self._expand_query(query),
            self._extract_filters(query),
        )
        
        result = QueryClassification(
            original_query=query,
            expanded_query=expanded_query,
            query_type=query_type,
            filters=filters,
        )
        
        logger.info(
            f"Query processed: type={query_type.value}, "
            f"has_filters={filters.has_filters()}, "
            f"expanded_length={len(expanded_query)}"
        )
        
        return result
    
    def process_sync(self, query: str) -> QueryClassification:
        """Synchronous version of process."""
        import asyncio
        return asyncio.run(self.process(query))
    
    async def _classify_query(self, query: str) -> QueryType:
        """Classify the query type."""
        if not settings.query_classification_enabled:
            return QueryType.SYNTHESIS
        
        try:
            llm = self._get_llm()
            prompt = QUERY_CLASSIFICATION_PROMPT.format(query=query)
            
            response = await llm.acomplete(prompt)
            classification = response.text.strip().lower()
            
            # Map to enum
            type_map = {
                "simple": QueryType.SIMPLE,
                "lookup": QueryType.LOOKUP,
                "synthesis": QueryType.SYNTHESIS,
                "comparison": QueryType.COMPARISON,
                "methodology": QueryType.METHODOLOGY,
            }
            
            return type_map.get(classification, QueryType.SYNTHESIS)
            
        except Exception as e:
            logger.warning(f"Query classification failed: {e}")
            return QueryType.SYNTHESIS
    
    async def _expand_query(self, query: str) -> str:
        """Expand query with synonyms and related terms."""
        if not settings.query_expansion_enabled:
            return query
        
        try:
            llm = self._get_llm()
            prompt = QUERY_EXPANSION_PROMPT.format(query=query)
            
            response = await llm.acomplete(prompt)
            expanded = response.text.strip()
            
            # Sanity check - expansion shouldn't be too long
            if len(expanded) > len(query) * 5:
                logger.warning("Query expansion too long, truncating")
                expanded = expanded[:len(query) * 5]
            
            return expanded
            
        except Exception as e:
            logger.warning(f"Query expansion failed: {e}")
            return query
    
    async def _extract_filters(self, query: str) -> ExtractedFilters:
        """Extract metadata filters from query."""
        try:
            llm = self._get_llm()
            prompt = METADATA_EXTRACTION_PROMPT.format(query=query)
            
            response = await llm.acomplete(prompt)
            
            # Parse JSON response
            try:
                data = json.loads(response.text.strip())
            except json.JSONDecodeError:
                # Try to extract JSON from response
                import re
                json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    return ExtractedFilters()
            
            return ExtractedFilters(
                year_min=data.get("year_min"),
                year_max=data.get("year_max"),
                sectors=data.get("sectors", []),
                countries=data.get("countries", []),
                study_types=data.get("study_types", []),
                target_populations=data.get("target_populations", []),
                confidence_level=data.get("confidence_level"),
            )
            
        except Exception as e:
            logger.warning(f"Filter extraction failed: {e}")
            return ExtractedFilters()

    async def decompose_query(self, query: str) -> List[str]:
        """
        Decompose a complex query into simpler sub-queries.
        
        Query Decomposition improves retrieval for complex queries by:
        1. Breaking comparisons into individual queries
        2. Separating multi-aspect questions
        3. Allowing more focused retrieval for each aspect
        
        Args:
            query: Original user query
            
        Returns:
            List of sub-queries (empty if no decomposition needed)
        """
        if not getattr(settings, 'query_decomposition_enabled', True):
            return []
        
        try:
            llm = self._get_llm()
            prompt = QUERY_DECOMPOSITION_PROMPT.format(query=query)
            
            response = await llm.acomplete(prompt)
            
            # Parse JSON response
            try:
                data = json.loads(response.text.strip())
            except json.JSONDecodeError:
                # Try to extract JSON from response
                import re
                json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    return []
            
            should_decompose = data.get("should_decompose", False)
            sub_queries = data.get("sub_queries", [])
            reason = data.get("reason", "")
            
            if should_decompose and sub_queries:
                logger.info(f"Query decomposed into {len(sub_queries)} sub-queries: {reason}")
                logger.debug(f"Sub-queries: {sub_queries}")
                return sub_queries
            
            return []
            
        except Exception as e:
            logger.warning(f"Query decomposition failed: {e}")
            return []
    
    def decompose_query_sync(self, query: str) -> List[str]:
        """Synchronous version of decompose_query."""
        import asyncio
        return asyncio.run(self.decompose_query(query))

    async def generate_step_back_query(self, query: str) -> Optional[str]:
        """
        Generate a step-back query for specific questions.
        
        Step-Back Prompting asks a more general question first to provide
        broader context before retrieving for the specific question.
        
        Example:
            "What's the effect size in Bossuroy 2024?" 
            → Step-back: "What outcomes does Bossuroy 2024 measure?"
        
        Args:
            query: Original user query
            
        Returns:
            Step-back query string, or None if not needed
            
        Reference: Step-Back Prompting (https://arxiv.org/abs/2310.06117)
        """
        if not getattr(settings, 'step_back_prompting_enabled', True):
            return None
        
        try:
            llm = self._get_llm()
            prompt = STEP_BACK_PROMPT.format(query=query)
            
            response = await llm.acomplete(prompt)
            
            # Parse JSON response
            try:
                data = json.loads(response.text.strip())
            except json.JSONDecodeError:
                import re
                json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    return None
            
            should_step_back = data.get("should_step_back", False)
            step_back_query = data.get("step_back_query")
            reason = data.get("reason", "")
            
            if should_step_back and step_back_query:
                logger.info(f"Step-back query generated: {reason}")
                logger.debug(f"Step-back: '{step_back_query}'")
                return step_back_query
            
            return None
            
        except Exception as e:
            logger.warning(f"Step-back prompting failed: {e}")
            return None
    
    def generate_step_back_query_sync(self, query: str) -> Optional[str]:
        """Synchronous version of generate_step_back_query."""
        import asyncio
        return asyncio.run(self.generate_step_back_query(query))

    async def generate_query_variants(
        self, 
        query: str, 
        num_variants: int = 3,
    ) -> List[str]:
        """
        Generate alternative phrasings of a query for RAG-Fusion.
        
        Multi-Query RAG-Fusion improves recall by retrieving with multiple
        query variants and fusing results with Reciprocal Rank Fusion (RRF).
        
        Args:
            query: Original user query
            num_variants: Number of variants to generate (default: 3)
            
        Returns:
            List of query variants (always includes original query first)
            
        Reference: RAG-Fusion paper (https://arxiv.org/abs/2402.03367)
        """
        # Always include original query
        variants = [query]
        
        if not settings.multi_query_enabled:
            return variants
        
        try:
            llm = self._get_llm()
            prompt = QUERY_VARIANTS_PROMPT.format(
                query=query,
                num_variants=num_variants,
            )
            
            response = await llm.acomplete(prompt)
            
            # Parse JSON array response
            try:
                generated = json.loads(response.text.strip())
                if isinstance(generated, list):
                    # Filter out empty strings and duplicates
                    for v in generated:
                        if v and isinstance(v, str) and v.strip() != query.strip():
                            variants.append(v.strip())
            except json.JSONDecodeError:
                # Try to extract JSON array from response
                import re
                json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
                if json_match:
                    generated = json.loads(json_match.group())
                    for v in generated:
                        if v and isinstance(v, str) and v.strip() != query.strip():
                            variants.append(v.strip())
            
            # Limit to requested number + original
            variants = variants[:num_variants + 1]
            
            logger.info(f"Generated {len(variants)} query variants for RAG-Fusion")
            logger.debug(f"Query variants: {variants}")
            
            return variants
            
        except Exception as e:
            logger.warning(f"Query variant generation failed: {e}, using original query only")
            return [query]

    def generate_query_variants_sync(self, query: str, num_variants: int = 3) -> List[str]:
        """Synchronous version of generate_query_variants."""
        import asyncio
        return asyncio.run(self.generate_query_variants(query, num_variants))


# Domain-specific query expansion rules (fallback if LLM fails)
EXPANSION_RULES: Dict[str, List[str]] = {
    # Acronyms
    "cct": ["conditional cash transfer", "cash transfer program"],
    "uct": ["unconditional cash transfer", "cash transfer"],
    "rct": ["randomized controlled trial", "randomized experiment"],
    "did": ["difference-in-differences", "difference in difference"],
    "iv": ["instrumental variable", "instrumental variables"],
    "psa": ["propensity score analysis", "propensity score matching"],
    
    # Sectors
    "education": ["schooling", "learning", "enrollment", "school"],
    "health": ["healthcare", "medical", "disease", "nutrition"],
    "agriculture": ["farming", "crop", "livestock", "agricultural"],
    "wash": ["water sanitation hygiene", "water supply", "sanitation"],
    "governance": ["government", "public sector", "institutional"],
    
    # Interventions
    "microfinance": ["microcredit", "microloans", "small loans"],
    "deworming": ["mass drug administration", "anthelminthic"],
    "school meals": ["school feeding", "midday meal", "food program"],
}


def rule_based_expansion(query: str) -> str:
    """
    Fallback rule-based query expansion.
    
    Uses predefined rules for common acronyms and terms.
    """
    query_lower = query.lower()
    expansions = []
    
    for term, synonyms in EXPANSION_RULES.items():
        if term in query_lower:
            expansions.extend(synonyms)
    
    if expansions:
        return f"{query} {' '.join(expansions)}"
    return query
