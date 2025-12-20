"""
DevChat v2.0 - Query Clarifier

Detects vague/broad queries and suggests clarifications.
For impact evaluation research, a good query should specify:
- Intervention type (what was done)
- Outcome of interest (what was measured)
- Context (where/when/for whom)

Vague queries like "poverty reduction" get transformed into a clarifying dialogue.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import json

from src.config.settings import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass 
class ClarificationSuggestion:
    """A suggested clarification for a vague query."""
    dimension: str  # intervention, outcome, context, population
    question: str  # Question to ask user
    examples: List[str]  # Example answers


@dataclass
class QueryAnalysis:
    """Result of analyzing whether a query needs clarification."""
    needs_clarification: bool
    reason: str
    suggestions: List[ClarificationSuggestion]
    
    # What we detected in the query
    has_intervention: bool = False
    has_outcome: bool = False  
    has_context: bool = False
    
    # Suggested refined query if user wants to proceed anyway
    suggested_refinement: Optional[str] = None


# Common intervention keywords
INTERVENTION_KEYWORDS = {
    'cash transfer', 'cct', 'uct', 'conditional cash', 'unconditional cash',
    'microfinance', 'microcredit', 'loan', 'savings group',
    'school meal', 'feeding program', 'nutrition program',
    'vaccination', 'immunization', 'health intervention',
    'training program', 'skills training', 'job training',
    'scholarship', 'education subsidy', 'tuition waiver',
    'water treatment', 'sanitation', 'wash intervention',
    'agricultural extension', 'fertilizer subsidy', 'irrigation',
    'mobile money', 'digital payment', 'financial inclusion',
    'social protection', 'safety net', 'insurance program',
}

# Common outcome keywords  
OUTCOME_KEYWORDS = {
    'income', 'earnings', 'wages', 'employment', 'labor',
    'education', 'enrollment', 'attendance', 'test scores', 'learning',
    'health', 'nutrition', 'mortality', 'morbidity', 'stunting',
    'food security', 'consumption', 'expenditure',
    'poverty', 'welfare', 'living standards',
    'empowerment', 'decision-making', 'gender',
    'savings', 'assets', 'investment',
    'child development', 'cognitive', 'socio-emotional',
}


class QueryClarifier:
    """
    Analyzes queries and suggests clarifications for vague ones.
    
    For impact evaluation research, we need specificity about:
    1. What intervention was tested
    2. What outcomes were measured
    3. What context/population was studied
    """
    
    def __init__(self):
        self._llm = None
    
    def _get_llm(self):
        """Lazy-load LLM."""
        if self._llm is None:
            try:
                from llama_index.llms.openai_like import OpenAILike
                self._llm = OpenAILike(
                    model="openai/gpt-4o-mini",
                    api_key=settings.openrouter_api_key,
                    api_base=settings.openrouter_base_url,
                    temperature=0.1,
                    max_tokens=1000,
                    is_chat_model=True,
                )
            except Exception as e:
                logger.error(f"Failed to initialize clarifier LLM: {e}")
        return self._llm
    
    def analyze_query_simple(self, query: str) -> QueryAnalysis:
        """
        Simple rule-based analysis (fast, no LLM call).
        
        Checks if query contains intervention + outcome specificity.
        """
        query_lower = query.lower()
        
        # Check for intervention specificity
        has_intervention = any(kw in query_lower for kw in INTERVENTION_KEYWORDS)
        
        # Check for outcome specificity  
        has_outcome = any(kw in query_lower for kw in OUTCOME_KEYWORDS)
        
        # Check for context (country, region, population)
        has_context = any([
            any(word in query_lower for word in ['africa', 'asia', 'latin america', 'india', 'kenya', 'bangladesh', 'brazil', 'mexico']),
            any(word in query_lower for word in ['women', 'children', 'youth', 'farmers', 'households', 'rural', 'urban']),
        ])
        
        # Determine if clarification needed
        word_count = len(query.split())
        
        if word_count <= 3 and not (has_intervention and has_outcome):
            # Very short query without specificity
            suggestions = self._generate_suggestions(
                query, has_intervention, has_outcome, has_context
            )
            return QueryAnalysis(
                needs_clarification=True,
                reason="Your query is quite broad. To find the most relevant evidence, it helps to be more specific.",
                suggestions=suggestions,
                has_intervention=has_intervention,
                has_outcome=has_outcome,
                has_context=has_context,
                suggested_refinement=self._suggest_refinement(query),
            )
        
        return QueryAnalysis(
            needs_clarification=False,
            reason="Query is specific enough",
            suggestions=[],
            has_intervention=has_intervention,
            has_outcome=has_outcome,
            has_context=has_context,
        )
    
    def _generate_suggestions(
        self, 
        query: str,
        has_intervention: bool,
        has_outcome: bool,
        has_context: bool,
    ) -> List[ClarificationSuggestion]:
        """Generate clarification suggestions based on what's missing."""
        suggestions = []
        
        if not has_intervention:
            suggestions.append(ClarificationSuggestion(
                dimension="intervention",
                question="What type of intervention or program are you interested in?",
                examples=[
                    "Cash transfer programs",
                    "Microfinance/microcredit",
                    "Education subsidies or scholarships",
                    "Health interventions (vaccination, nutrition)",
                    "Agricultural programs",
                    "Job training or skills programs",
                ]
            ))
        
        if not has_outcome:
            suggestions.append(ClarificationSuggestion(
                dimension="outcome",
                question="What outcomes or effects are you most interested in?",
                examples=[
                    "Income and employment",
                    "Education (enrollment, learning)",
                    "Health and nutrition",
                    "Poverty and welfare",
                    "Women's empowerment",
                    "Food security",
                ]
            ))
        
        if not has_context:
            suggestions.append(ClarificationSuggestion(
                dimension="context",
                question="Any specific context or population?",
                examples=[
                    "Sub-Saharan Africa",
                    "South Asia",
                    "Rural vs urban areas",
                    "Women or female-headed households",
                    "Children or youth",
                    "Smallholder farmers",
                ]
            ))
        
        return suggestions
    
    def _suggest_refinement(self, query: str) -> str:
        """Suggest a more specific version of the query."""
        query_lower = query.lower()
        
        # Common refinements for typical vague queries
        refinements = {
            'poverty': "What interventions reduce poverty? (e.g., 'impact of cash transfers on poverty')",
            'education': "What improves education outcomes? (e.g., 'effect of scholarships on enrollment')",
            'health': "What improves health outcomes? (e.g., 'impact of nutrition programs on child health')",
            'employment': "What increases employment? (e.g., 'effect of job training on employment')",
            'women': "What empowers women? (e.g., 'impact of microfinance on women's empowerment')",
        }
        
        for key, refinement in refinements.items():
            if key in query_lower:
                return refinement
        
        return f"Try being more specific, e.g., 'What is the impact of [intervention] on [outcome]?'"
    
    async def analyze_query_llm(self, query: str) -> QueryAnalysis:
        """
        LLM-based analysis for more nuanced understanding.
        
        Use when simple analysis is insufficient.
        """
        llm = self._get_llm()
        if llm is None:
            return self.analyze_query_simple(query)
        
        prompt = f"""Analyze this research query for an impact evaluation database.

QUERY: "{query}"

A good impact evaluation query should ideally specify:
1. INTERVENTION: What program/policy was tested
2. OUTCOME: What effects were measured
3. CONTEXT: Where/when/for whom (optional but helpful)

Analyze the query and respond in JSON:
{{
    "needs_clarification": true/false,
    "reason": "Why clarification is/isn't needed",
    "has_intervention": true/false,
    "has_outcome": true/false,
    "has_context": true/false,
    "clarifying_questions": [
        {{"dimension": "intervention/outcome/context", "question": "...", "examples": ["...", "..."]}}
    ],
    "suggested_refinement": "A more specific version of the query"
}}

Examples of queries that NEED clarification:
- "poverty reduction" → too broad, what intervention? what outcome?
- "education" → what aspect? enrollment? learning? what program?
- "impact in Africa" → impact of what? on what?

Examples of queries that DON'T need clarification:
- "impact of cash transfers on school enrollment in Africa"
- "do microfinance programs increase women's income?"
- "effectiveness of conditional cash transfers on child nutrition"

Return ONLY the JSON."""

        try:
            response = await llm.acomplete(prompt)
            text = response.text.strip()
            
            # Clean JSON
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0]
            elif '```' in text:
                text = text.split('```')[1].split('```')[0]
            
            data = json.loads(text)
            
            suggestions = []
            for q in data.get('clarifying_questions', []):
                suggestions.append(ClarificationSuggestion(
                    dimension=q.get('dimension', 'general'),
                    question=q.get('question', ''),
                    examples=q.get('examples', []),
                ))
            
            return QueryAnalysis(
                needs_clarification=data.get('needs_clarification', False),
                reason=data.get('reason', ''),
                suggestions=suggestions,
                has_intervention=data.get('has_intervention', False),
                has_outcome=data.get('has_outcome', False),
                has_context=data.get('has_context', False),
                suggested_refinement=data.get('suggested_refinement'),
            )
            
        except Exception as e:
            logger.error(f"LLM query analysis failed: {e}")
            return self.analyze_query_simple(query)


def format_clarification_response(analysis: QueryAnalysis) -> str:
    """Format clarification suggestions as a user-friendly response."""
    if not analysis.needs_clarification:
        return ""
    
    lines = [
        "🔍 **Your query could be more specific**",
        "",
        analysis.reason,
        "",
    ]
    
    for i, suggestion in enumerate(analysis.suggestions, 1):
        lines.append(f"**{suggestion.question}**")
        for example in suggestion.examples[:4]:
            lines.append(f"  • {example}")
        lines.append("")
    
    if analysis.suggested_refinement:
        lines.append(f"💡 *Suggestion: {analysis.suggested_refinement}*")
    
    lines.append("")
    lines.append("You can proceed with your current query, or refine it for more targeted results.")
    
    return "\n".join(lines)
