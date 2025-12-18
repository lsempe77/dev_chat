"""
DevChat v2.0 SOTA - Generation Tests

Tests for model routing, synthesis, and citations.
"""

import pytest

from src.generation.router import CostTracker, ModelRouter, ModelTier, RoutingDecision
from src.generation.citations import Citation, CitationFormatter, add_citations_to_answer
from src.retrieval.query_processor import QueryType


class TestModelRouter:
    """Tests for ModelRouter."""
    
    def test_simple_query_routes_to_fast(self):
        """Simple queries should use fast model."""
        router = ModelRouter()
        decision = router.route(query_type=QueryType.SIMPLE)
        
        assert decision.tier == ModelTier.FAST
        assert "haiku" in decision.model_name.lower() or "mini" in decision.model_name.lower()
    
    def test_comparison_routes_to_reasoning(self):
        """Comparison queries should use reasoning model."""
        router = ModelRouter()
        decision = router.route(query_type=QueryType.COMPARISON)
        
        assert decision.tier == ModelTier.REASONING
        assert "sonnet" in decision.model_name.lower() or "4o" in decision.model_name.lower()
    
    def test_synthesis_with_many_studies_routes_to_reasoning(self):
        """Synthesis with many studies should use reasoning model."""
        router = ModelRouter()
        decision = router.route(
            query_type=QueryType.SYNTHESIS,
            num_studies=5,
        )
        
        assert decision.tier == ModelTier.REASONING
    
    def test_large_context_routes_to_reasoning(self):
        """Large context should use reasoning model."""
        router = ModelRouter()
        decision = router.route(
            query_type=QueryType.LOOKUP,
            context_length=10000,
        )
        
        assert decision.tier == ModelTier.REASONING
    
    def test_cost_factor_differs(self):
        """Reasoning model should have higher cost factor."""
        router = ModelRouter()
        
        fast_decision = router.route(query_type=QueryType.SIMPLE)
        reasoning_decision = router.route(query_type=QueryType.COMPARISON)
        
        assert reasoning_decision.estimated_cost_factor > fast_decision.estimated_cost_factor


class TestCostTracker:
    """Tests for CostTracker."""
    
    def test_track_single_call(self):
        """Test tracking a single LLM call."""
        tracker = CostTracker()
        cost = tracker.track(
            model="claude-3-5-haiku-20241022",
            input_tokens=1000,
            output_tokens=500,
        )
        
        assert cost > 0
        assert len(tracker.calls) == 1
    
    def test_summary(self):
        """Test getting usage summary."""
        tracker = CostTracker()
        tracker.track("gpt-4o-mini", 1000, 500)
        tracker.track("gpt-4o-mini", 2000, 1000)
        
        summary = tracker.get_summary()
        
        assert summary["total_calls"] == 2
        assert summary["total_input_tokens"] == 3000
        assert summary["total_output_tokens"] == 1500


class TestCitation:
    """Tests for Citation class."""
    
    def test_format_apa(self):
        """Test APA citation formatting."""
        citation = Citation(
            study_id="123",
            title="Effects of Cash Transfers",
            authors="Smith, J., Jones, M.",
            year=2023,
        )
        
        formatted = CitationFormatter.format_apa(citation)
        
        assert "Smith" in formatted
        assert "2023" in formatted
        assert "Effects of Cash Transfers" in formatted
    
    def test_format_inline(self):
        """Test inline citation formatting."""
        citation = Citation(
            study_id="123",
            title="Effects of Cash Transfers",
            authors="Smith, J.",
            year=2023,
        )
        
        formatted = CitationFormatter.format_inline(citation)
        
        assert "Smith" in formatted
        assert "2023" in formatted
        assert formatted.startswith("(")
        assert formatted.endswith(")")
    
    def test_format_inline_no_author(self):
        """Test inline formatting without author."""
        citation = Citation(
            study_id="123",
            title="A Very Long Study Title That Should Be Truncated",
            year=2023,
        )
        
        formatted = CitationFormatter.format_inline(citation)
        
        assert "2023" in formatted
        assert len(formatted) < 100


class TestCitationFormatter:
    """Tests for CitationFormatter."""
    
    def test_format_reference_list(self):
        """Test generating reference list."""
        citations = [
            Citation(study_id="1", title="Study One", year=2023),
            Citation(study_id="2", title="Study Two", year=2021),
            Citation(study_id="3", title="Study Three", year=2022),
        ]
        
        ref_list = CitationFormatter.format_reference_list(citations)
        
        assert "## References" in ref_list
        assert "Study One" in ref_list
        assert "Study Two" in ref_list
    
    def test_format_reference_list_sorted(self):
        """Test reference list is sorted by year descending."""
        citations = [
            Citation(study_id="1", title="Old Study", year=2019),
            Citation(study_id="2", title="New Study", year=2023),
        ]
        
        ref_list = CitationFormatter.format_reference_list(citations)
        
        # New study should appear before old study
        new_idx = ref_list.find("New Study")
        old_idx = ref_list.find("Old Study")
        assert new_idx < old_idx
    
    def test_from_dict(self):
        """Test creating Citation from dictionary."""
        data = {
            "study_id": "123",
            "title": "Test Study",
            "year": 2023,
            "sector": "education",
        }
        
        citation = CitationFormatter.from_dict(data)
        
        assert citation.study_id == "123"
        assert citation.title == "Test Study"
        assert citation.year == 2023
        assert citation.sector == "education"


class TestAddCitations:
    """Tests for add_citations_to_answer function."""
    
    def test_add_citations_to_answer(self):
        """Test adding citations to an answer."""
        answer = "Cash transfers improve education outcomes."
        citations = [
            {"study_id": "1", "title": "CCT Study", "year": 2023},
        ]
        
        result = add_citations_to_answer(answer, citations)
        
        assert answer in result
        assert "References" in result
        assert "CCT Study" in result
    
    def test_add_citations_empty_list(self):
        """Test with empty citation list."""
        answer = "This is an answer."
        
        result = add_citations_to_answer(answer, [])
        
        assert result == answer
