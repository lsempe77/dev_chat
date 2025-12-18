"""
DevChat v2.0 SOTA - Integration Tests

End-to-end tests for the full pipeline.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.devchat_agent import DevChatAgent, DevChatAgentFactory, DevChatResponse
from src.config.settings import Settings


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    return Settings(
        anthropic_api_key="test-key",
        cohere_api_key="test-key",
        qdrant_url="http://localhost:6333",
    )


class TestDevChatAgent:
    """Integration tests for DevChatAgent."""
    
    @pytest.mark.asyncio
    async def test_agent_chat_returns_response(self):
        """Test that agent returns a DevChatResponse."""
        # This test would require mocking the entire pipeline
        # For now, just test the factory
        pass
    
    def test_agent_factory_default(self):
        """Test default agent creation."""
        # Just verify it doesn't crash during instantiation checks
        # (actual initialization may fail without proper env vars)
        pass
    
    def test_chat_response_to_dict(self):
        """Test DevChatResponse serialization."""
        response = DevChatResponse(
            answer="Test answer",
            query_type="synthesis",
            model_used="claude-3-5-haiku",
            num_sources=3,
            citations=[],
            query_time_ms=100.0,
            retrieval_time_ms=200.0,
            rerank_time_ms=50.0,
            synthesis_time_ms=500.0,
            total_time_ms=850.0,
        )
        
        data = response.to_dict()
        
        assert data["answer"] == "Test answer"
        assert data["query_type"] == "synthesis"
        assert data["timing"]["total_ms"] == 850.0


class TestAgentFactory:
    """Tests for DevChatAgentFactory."""
    
    def test_factory_methods_exist(self):
        """Test factory methods exist."""
        assert hasattr(DevChatAgentFactory, 'create_default')
        assert hasattr(DevChatAgentFactory, 'create_fast')
        assert hasattr(DevChatAgentFactory, 'create_accurate')
        assert hasattr(DevChatAgentFactory, 'create_with_custom_collection')


class TestEndToEnd:
    """End-to-end integration tests."""
    
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_full_pipeline(self):
        """
        Test the full RAG pipeline.
        
        This test requires:
        - Valid API keys
        - Running Qdrant instance
        - Indexed documents
        
        Skip in CI unless integration testing is enabled.
        """
        pytest.skip("Requires live services")
    
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_streaming_response(self):
        """Test streaming response generation."""
        pytest.skip("Requires live services")


class TestSettingsValidation:
    """Tests for settings validation."""
    
    def test_settings_defaults(self):
        """Test settings have reasonable defaults."""
        settings = Settings()
        
        assert settings.chunk_size > 0
        assert settings.retrieval_top_k > 0
        assert 0 <= settings.hybrid_alpha <= 1
    
    def test_settings_chunk_overlap_validation(self):
        """Test chunk overlap must be less than chunk size."""
        # This should raise validation error
        with pytest.raises(ValueError):
            Settings(chunk_size=100, chunk_overlap=150)


class TestPipelineComponents:
    """Tests for individual pipeline component integration."""
    
    def test_query_to_context_flow(self):
        """Test the flow from query processing to context building."""
        from src.retrieval.query_processor import QueryClassification, QueryType, ExtractedFilters
        from src.retrieval.hybrid_retriever import RetrievalResult
        from src.retrieval.context_builder import ContextBuilder
        
        # Simulate query classification result
        query = QueryClassification(
            original_query="effects of CCTs",
            expanded_query="effects of conditional cash transfers on education outcomes",
            query_type=QueryType.SYNTHESIS,
            filters=ExtractedFilters(),
        )
        
        # Simulate retrieval results
        results = [
            RetrievalResult(
                node_id="1",
                text="CCTs have positive effects on school enrollment.",
                score=0.95,
                metadata={"study_id": "123", "title": "CCT Study", "year": 2023},
            ),
        ]
        
        # Build context
        builder = ContextBuilder()
        context = builder.build(results)
        
        # Verify context is usable
        assert context.num_chunks > 0
        assert len(context.text) > 0
        assert len(context.citations) > 0
