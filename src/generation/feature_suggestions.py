"""
DevChat v2.0 SOTA - Feature Suggestions Generator

Generates creative and actionable feature suggestions based on RAG project context.
Uses LLM to analyze project data and suggest relevant features.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from enum import Enum

from src.config.settings import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class FeatureCategory(str, Enum):
    """Categories for feature suggestions."""
    RETRIEVAL = "retrieval"
    ANALYSIS = "analysis"
    VISUALIZATION = "visualization"
    EXPORT = "export"
    COLLABORATION = "collaboration"
    AUTOMATION = "automation"
    QUALITY = "quality"
    INTEGRATION = "integration"


@dataclass
class FeatureSuggestion:
    """A single feature suggestion."""
    id: str
    title: str
    description: str
    category: FeatureCategory
    impact: str  # "high", "medium", "low"
    effort: str  # "high", "medium", "low"
    rationale: str  # Why this feature would help

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "impact": self.impact,
            "effort": self.effort,
            "rationale": self.rationale,
        }


FEATURE_SUGGESTIONS_PROMPT = """You are a product strategist for a RAG (Retrieval-Augmented Generation) research platform called DevChat.

DevChat helps researchers:
- Query academic documents with natural language
- Get citation-grounded answers from a corpus of studies
- Filter by year, country, sector, and study type
- Compare studies side-by-side

CURRENT PROJECT CONTEXT:
- Project Name: {project_name}
- Document Count: {document_count}
- Total Queries: {query_count}
- Common Topics: {common_topics}
- User Feedback: {user_feedback}

Based on this context, generate exactly 10 creative and actionable feature suggestions.

For each feature, provide:
1. **title**: Short, catchy name (3-5 words)
2. **description**: One-sentence description of what it does
3. **category**: One of: retrieval, analysis, visualization, export, collaboration, automation, quality, integration
4. **impact**: Expected user value (high/medium/low)
5. **effort**: Implementation complexity (high/medium/low)
6. **rationale**: Why this would help users based on the project context

Focus on features that would:
- Improve research efficiency
- Enhance evidence synthesis quality
- Enable new types of analysis
- Improve user experience

Respond with a JSON array of 10 feature objects. No explanation, just the JSON."""


class FeatureSuggestionsGenerator:
    """Generates feature suggestions using LLM analysis."""

    def __init__(self):
        self.llm = None

    async def _get_llm(self):
        """Lazy-load LLM client."""
        if self.llm is None:
            from llama_index.llms.openai_like import OpenAILike

            self.llm = OpenAILike(
                model=settings.llm_fast_model,
                api_base=settings.openrouter_base_url,
                api_key=settings.openrouter_api_key,
                temperature=0.8,  # Higher temperature for creativity
                max_tokens=2000,
            )
        return self.llm

    async def generate_suggestions(
        self,
        project_name: str = "DevChat RAG Project",
        document_count: int = 0,
        query_count: int = 0,
        common_topics: Optional[List[str]] = None,
        user_feedback: Optional[str] = None,
    ) -> List[FeatureSuggestion]:
        """
        Generate creative feature suggestions based on project context.

        Args:
            project_name: Name of the RAG project
            document_count: Number of documents in the project
            query_count: Total queries made
            common_topics: List of common topics/sectors
            user_feedback: Any user feedback or pain points

        Returns:
            List of 10 FeatureSuggestion objects
        """
        # Build context for prompt
        topics_str = ", ".join(common_topics) if common_topics else "general research topics"
        feedback_str = user_feedback or "No specific feedback provided"

        prompt = FEATURE_SUGGESTIONS_PROMPT.format(
            project_name=project_name,
            document_count=document_count,
            query_count=query_count,
            common_topics=topics_str,
            user_feedback=feedback_str,
        )

        try:
            llm = await self._get_llm()
            response = await llm.acomplete(prompt)

            # Parse JSON response
            import json
            from src.utils.json_utils import extract_json_from_text

            suggestions_data = extract_json_from_text(response.text)

            if not suggestions_data or not isinstance(suggestions_data, list):
                logger.warning("Failed to parse feature suggestions, using defaults")
                return self._get_default_suggestions()

            # Convert to FeatureSuggestion objects
            suggestions = []
            for i, item in enumerate(suggestions_data[:10]):
                try:
                    category = item.get("category", "analysis")
                    if category not in [c.value for c in FeatureCategory]:
                        category = "analysis"

                    suggestion = FeatureSuggestion(
                        id=f"feature-{i+1}",
                        title=item.get("title", f"Feature {i+1}"),
                        description=item.get("description", "No description provided"),
                        category=FeatureCategory(category),
                        impact=item.get("impact", "medium"),
                        effort=item.get("effort", "medium"),
                        rationale=item.get("rationale", "Improves user experience"),
                    )
                    suggestions.append(suggestion)
                except Exception as e:
                    logger.warning(f"Failed to parse suggestion {i}: {e}")

            # Ensure we have 10 suggestions
            if len(suggestions) < 10:
                defaults = self._get_default_suggestions()
                suggestions.extend(defaults[:(10 - len(suggestions))])

            logger.info(f"Generated {len(suggestions)} feature suggestions")
            return suggestions[:10]

        except Exception as e:
            logger.error(f"Failed to generate feature suggestions: {e}")
            return self._get_default_suggestions()

    def _get_default_suggestions(self) -> List[FeatureSuggestion]:
        """Return default feature suggestions as fallback."""
        defaults = [
            FeatureSuggestion(
                id="feature-1",
                title="Smart Query Autocomplete",
                description="AI-powered search suggestions based on document corpus and past queries",
                category=FeatureCategory.RETRIEVAL,
                impact="high",
                effort="medium",
                rationale="Helps users discover relevant documents faster",
            ),
            FeatureSuggestion(
                id="feature-2",
                title="Evidence Gap Map",
                description="Visual heatmap showing research coverage across topics and regions",
                category=FeatureCategory.VISUALIZATION,
                impact="high",
                effort="high",
                rationale="Identifies under-researched areas for future studies",
            ),
            FeatureSuggestion(
                id="feature-3",
                title="Automated Literature Review",
                description="Generate structured literature review documents from query results",
                category=FeatureCategory.EXPORT,
                impact="high",
                effort="medium",
                rationale="Saves researchers hours of manual synthesis work",
            ),
            FeatureSuggestion(
                id="feature-4",
                title="Citation Network Explorer",
                description="Interactive graph showing citation relationships between studies",
                category=FeatureCategory.VISUALIZATION,
                impact="medium",
                effort="high",
                rationale="Reveals influential papers and research lineages",
            ),
            FeatureSuggestion(
                id="feature-5",
                title="Methodology Comparison Tool",
                description="Side-by-side comparison of study designs and methods",
                category=FeatureCategory.ANALYSIS,
                impact="medium",
                effort="medium",
                rationale="Helps assess evidence quality and generalizability",
            ),
            FeatureSuggestion(
                id="feature-6",
                title="Real-time Collaboration",
                description="Share and annotate research findings with team members",
                category=FeatureCategory.COLLABORATION,
                impact="high",
                effort="high",
                rationale="Enables team-based evidence synthesis workflows",
            ),
            FeatureSuggestion(
                id="feature-7",
                title="Zotero Sync Enhancement",
                description="Two-way sync with Zotero for seamless bibliography management",
                category=FeatureCategory.INTEGRATION,
                impact="medium",
                effort="medium",
                rationale="Integrates with researchers' existing workflows",
            ),
            FeatureSuggestion(
                id="feature-8",
                title="Effect Size Calculator",
                description="Extract and standardize effect sizes across studies",
                category=FeatureCategory.ANALYSIS,
                impact="high",
                effort="high",
                rationale="Enables quantitative meta-analysis capabilities",
            ),
            FeatureSuggestion(
                id="feature-9",
                title="Weekly Research Digest",
                description="Automated email summaries of new relevant studies",
                category=FeatureCategory.AUTOMATION,
                impact="medium",
                effort="low",
                rationale="Keeps researchers updated without manual checking",
            ),
            FeatureSuggestion(
                id="feature-10",
                title="Quality Score Dashboard",
                description="Visual dashboard showing answer quality metrics over time",
                category=FeatureCategory.QUALITY,
                impact="medium",
                effort="low",
                rationale="Builds trust through transparency in AI performance",
            ),
        ]
        return defaults


# Singleton instance
_generator: Optional[FeatureSuggestionsGenerator] = None


def get_feature_suggestions_generator() -> FeatureSuggestionsGenerator:
    """Get singleton feature suggestions generator."""
    global _generator
    if _generator is None:
        _generator = FeatureSuggestionsGenerator()
    return _generator
