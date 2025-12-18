"""
DevChat v2.0 SOTA - Retrieval Tests

Tests for query processing, hybrid retrieval, and reranking.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.retrieval.query_processor import (
    ExtractedFilters,
    QueryClassification,
    QueryProcessor,
    QueryType,
    rule_based_expansion,
)
from src.retrieval.hybrid_retriever import HybridRetriever, RetrievalResult
from src.retrieval.reranker import CohereReranker, NoOpReranker
from src.retrieval.context_builder import ContextBuilder, FormattedContext


class TestQueryProcessor:
    """Tests for QueryProcessor."""
    
    def test_rule_based_expansion_cct(self):
        """Test CCT acronym expansion."""
        result = rule_based_expansion("What are the effects of CCTs?")
        assert "conditional cash transfer" in result.lower()
    
    def test_rule_based_expansion_rct(self):
        """Test RCT acronym expansion."""
        result = rule_based_expansion("Find RCT studies")
        assert "randomized controlled trial" in result.lower()
    
    def test_rule_based_expansion_no_match(self):
        """Test no expansion when no matches."""
        query = "What is the weather today?"
        result = rule_based_expansion(query)
        assert result == query
    
    def test_extracted_filters_has_filters(self):
        """Test has_filters method."""
        empty_filters = ExtractedFilters()
        assert not empty_filters.has_filters()
        
        with_year = ExtractedFilters(year_min=2020)
        assert with_year.has_filters()
        
        with_sector = ExtractedFilters(sectors=["education"])
        assert with_sector.has_filters()


class TestExtractedFilters:
    """Tests for ExtractedFilters."""
    
    def test_to_qdrant_filter_empty(self):
        """Test empty filters produce no Qdrant filter."""
        filters = ExtractedFilters()
        result = filters.to_qdrant_filter()
        assert result is None
    
    def test_to_qdrant_filter_year(self):
        """Test year filter conversion."""
        filters = ExtractedFilters(year_min=2020, year_max=2025)
        result = filters.to_qdrant_filter()
        assert result is not None
    
    def test_to_qdrant_filter_sector(self):
        """Test sector filter conversion."""
        filters = ExtractedFilters(sectors=["education", "health"])
        result = filters.to_qdrant_filter()
        assert result is not None


class TestRetrievalResult:
    """Tests for RetrievalResult."""
    
    def test_retrieval_result_properties(self):
        """Test RetrievalResult property access."""
        result = RetrievalResult(
            node_id="123",
            text="Test text",
            score=0.95,
            metadata={
                "study_id": "456",
                "title": "Test Study",
                "year": 2023,
            },
        )
        
        assert result.study_id == "456"
        assert result.title == "Test Study"
        assert result.year == 2023


class TestNoOpReranker:
    """Tests for NoOpReranker."""
    
    @pytest.mark.asyncio
    async def test_noop_reranker_truncates(self):
        """Test NoOp reranker just truncates."""
        reranker = NoOpReranker()
        
        results = [
            RetrievalResult(node_id=str(i), text=f"Text {i}", score=0.9-i*0.1, metadata={})
            for i in range(10)
        ]
        
        reranked = await reranker.rerank("query", results, top_n=5)
        
        assert len(reranked) == 5
        assert reranked[0].node_id == "0"


class TestContextBuilder:
    """Tests for ContextBuilder."""
    
    def test_build_empty_results(self):
        """Test building context with no results."""
        builder = ContextBuilder()
        result = builder.build([])
        
        assert "No relevant studies found" in result.text
        assert result.num_chunks == 0
        assert result.num_studies == 0
    
    def test_build_with_results(self):
        """Test building context with results."""
        results = [
            RetrievalResult(
                node_id="1",
                text="This is the study content.",
                score=0.95,
                metadata={
                    "study_id": "123",
                    "title": "Test Study",
                    "year": 2023,
                },
            ),
        ]
        
        builder = ContextBuilder()
        context = builder.build(results)
        
        assert context.num_chunks == 1
        assert context.num_studies == 1
        assert len(context.citations) == 1
        assert "Test Study" in context.text
    
    def test_build_grouped_by_study(self):
        """Test grouping by study."""
        results = [
            RetrievalResult(
                node_id="1",
                text="Chunk 1 from study A",
                score=0.95,
                metadata={"study_id": "A", "title": "Study A"},
            ),
            RetrievalResult(
                node_id="2",
                text="Chunk 2 from study A",
                score=0.90,
                metadata={"study_id": "A", "title": "Study A"},
            ),
            RetrievalResult(
                node_id="3",
                text="Chunk 1 from study B",
                score=0.85,
                metadata={"study_id": "B", "title": "Study B"},
            ),
        ]
        
        builder = ContextBuilder(group_by_study=True)
        context = builder.build(results)
        
        assert context.num_studies == 2
        assert len(context.citations) == 2
    
    def test_smart_truncate(self):
        """Test smart truncation at sentence boundaries."""
        builder = ContextBuilder(max_context_length=100)
        
        long_text = "This is a sentence. " * 20
        truncated = builder._smart_truncate(long_text)
        
        assert len(truncated) <= 150  # Allow some buffer for notice
        assert "[Context truncated" in truncated


class TestQueryClassification:
    """Tests for QueryClassification dataclass."""
    
    def test_primary_query_returns_expanded(self):
        """Test primary_query returns expanded when available."""
        qc = QueryClassification(
            original_query="CCT effects",
            expanded_query="conditional cash transfer effects on education",
            query_type=QueryType.SYNTHESIS,
            filters=ExtractedFilters(),
        )
        
        assert qc.primary_query == "conditional cash transfer effects on education"
    
    def test_primary_query_fallback(self):
        """Test primary_query falls back to original."""
        qc = QueryClassification(
            original_query="CCT effects",
            expanded_query="",
            query_type=QueryType.SIMPLE,
            filters=ExtractedFilters(),
        )
        
        assert qc.primary_query == "CCT effects"
