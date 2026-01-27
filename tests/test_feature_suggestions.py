"""
Unit tests for Feature Suggestions Generator.

This test verifies the feature suggestions implementation works correctly.
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.generation.feature_suggestions import (
    FeatureSuggestionsGenerator,
    FeatureSuggestion,
    FeatureCategory,
    get_feature_suggestions_generator,
)


class TestFeatureSuggestionsGenerator:
    """Test suite for FeatureSuggestionsGenerator."""

    def test_get_default_suggestions(self):
        """Test that default suggestions are returned correctly."""
        generator = FeatureSuggestionsGenerator()
        suggestions = generator._get_default_suggestions()

        # Should return exactly 10 suggestions
        assert len(suggestions) == 10

        # Each suggestion should be a FeatureSuggestion
        for suggestion in suggestions:
            assert isinstance(suggestion, FeatureSuggestion)
            assert suggestion.id is not None
            assert suggestion.title is not None
            assert suggestion.description is not None
            assert isinstance(suggestion.category, FeatureCategory)
            assert suggestion.impact in ["high", "medium", "low"]
            assert suggestion.effort in ["high", "medium", "low"]
            assert suggestion.rationale is not None

        print(f"Default suggestions: {len(suggestions)} items returned")

    def test_suggestion_to_dict(self):
        """Test that FeatureSuggestion can be converted to dict."""
        suggestion = FeatureSuggestion(
            id="test-1",
            title="Test Feature",
            description="A test feature description",
            category=FeatureCategory.ANALYSIS,
            impact="high",
            effort="low",
            rationale="For testing purposes",
        )

        result = suggestion.to_dict()

        assert result["id"] == "test-1"
        assert result["title"] == "Test Feature"
        assert result["description"] == "A test feature description"
        assert result["category"] == "analysis"
        assert result["impact"] == "high"
        assert result["effort"] == "low"
        assert result["rationale"] == "For testing purposes"

    def test_singleton_generator(self):
        """Test that get_feature_suggestions_generator returns singleton."""
        gen1 = get_feature_suggestions_generator()
        gen2 = get_feature_suggestions_generator()
        assert gen1 is gen2

    def test_default_suggestions_have_diverse_categories(self):
        """Test that default suggestions cover multiple categories."""
        generator = FeatureSuggestionsGenerator()
        suggestions = generator._get_default_suggestions()

        categories = set(s.category for s in suggestions)

        # Should have at least 3 different categories
        assert len(categories) >= 3
        print(f"Categories covered: {[c.value for c in categories]}")

    def test_default_suggestions_have_varied_impact_effort(self):
        """Test that default suggestions have varied impact and effort levels."""
        generator = FeatureSuggestionsGenerator()
        suggestions = generator._get_default_suggestions()

        impacts = set(s.impact for s in suggestions)
        efforts = set(s.effort for s in suggestions)

        # Should have at least 2 different impact levels
        assert len(impacts) >= 2
        # Should have at least 2 different effort levels
        assert len(efforts) >= 2

        print(f"Impact levels: {impacts}")
        print(f"Effort levels: {efforts}")

    def test_feature_category_enum_values(self):
        """Test that FeatureCategory enum has expected values."""
        expected_categories = [
            "retrieval",
            "analysis",
            "visualization",
            "export",
            "collaboration",
            "automation",
            "quality",
            "integration",
        ]

        actual_categories = [c.value for c in FeatureCategory]

        for expected in expected_categories:
            assert expected in actual_categories, f"Missing category: {expected}"


class TestFeatureSuggestionsSchema:
    """Test the Pydantic schemas for feature suggestions."""

    def test_suggestion_item_structure(self):
        """Test that each suggestion has the expected structure."""
        generator = FeatureSuggestionsGenerator()
        suggestions = generator._get_default_suggestions()

        for suggestion in suggestions:
            # All required fields must be present and non-empty
            assert suggestion.id, "ID should not be empty"
            assert suggestion.title, "Title should not be empty"
            assert suggestion.description, "Description should not be empty"
            assert suggestion.rationale, "Rationale should not be empty"

            # Check that ID follows expected format
            assert suggestion.id.startswith("feature-"), f"ID should start with 'feature-': {suggestion.id}"

    def test_suggestion_json_serialization(self):
        """Test that suggestions can be JSON serialized."""
        import json

        generator = FeatureSuggestionsGenerator()
        suggestions = generator._get_default_suggestions()

        # Convert all to dict and then to JSON
        data = [s.to_dict() for s in suggestions]
        json_str = json.dumps(data)

        # Parse it back
        parsed = json.loads(json_str)

        assert len(parsed) == 10
        assert parsed[0]["id"] == "feature-1"

        print("JSON serialization successful")
        print(f"Sample JSON: {json.dumps(parsed[0], indent=2)}")


def run_verification():
    """Run all verification tests and print results."""
    print("=" * 60)
    print("Feature Suggestions Verification Test")
    print("=" * 60)

    # Test 1: Default suggestions
    print("\n1. Testing default suggestions generation...")
    generator = FeatureSuggestionsGenerator()
    suggestions = generator._get_default_suggestions()
    assert len(suggestions) == 10, f"Expected 10 suggestions, got {len(suggestions)}"
    print(f"   PASS: Got {len(suggestions)} suggestions")

    # Test 2: Suggestion structure
    print("\n2. Testing suggestion structure...")
    for i, s in enumerate(suggestions):
        assert s.id == f"feature-{i+1}", f"ID mismatch for suggestion {i}"
        assert len(s.title) > 0, f"Empty title for suggestion {i}"
        assert len(s.description) > 0, f"Empty description for suggestion {i}"
    print("   PASS: All suggestions have valid structure")

    # Test 3: Category diversity
    print("\n3. Testing category diversity...")
    categories = set(s.category.value for s in suggestions)
    print(f"   Categories: {categories}")
    assert len(categories) >= 3, f"Expected at least 3 categories, got {len(categories)}"
    print(f"   PASS: {len(categories)} unique categories")

    # Test 4: JSON serialization
    print("\n4. Testing JSON serialization...")
    import json
    data = [s.to_dict() for s in suggestions]
    json_output = json.dumps(data, indent=2)
    assert len(json_output) > 0
    print("   PASS: JSON serialization works")

    # Print sample output
    print("\n" + "=" * 60)
    print("Sample Feature Suggestions JSON Array:")
    print("=" * 60)
    print(json.dumps(data[:3], indent=2))

    print("\n" + "=" * 60)
    print("VERIFICATION COMPLETE - ALL TESTS PASSED")
    print("=" * 60)

    return True


if __name__ == "__main__":
    # Run verification
    success = run_verification()
    sys.exit(0 if success else 1)
