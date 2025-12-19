"""
DevChat v2.0 SOTA - Prompt Templates

All LLM prompts are centralized here for easy maintenance and A/B testing.
"""

from typing import Optional

# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

DEVCHAT_SYSTEM_PROMPT = """You are DevChat, a friendly and knowledgeable AI assistant \
specialized in exploring academic studies from 3ie's Development Evidence Portal.

Your expertise covers:
- Impact evaluations and systematic reviews
- Development interventions (education, health, livelihoods, governance)
- Research methodology and evidence synthesis

Guidelines:
1. Always base your answers on the retrieved study context provided
2. Cite specific studies with their titles and years when making claims
3. Acknowledge limitations and conflicting findings when they exist
4. If the context doesn't contain relevant information, clearly state this
5. Be concise but thorough - prioritize clarity over length

Response Structure (when discussing specific studies):
- **Key Finding**: The main takeaway
- **Evidence**: Supporting details from the study
- **Context**: Methodology, location, population
- **Limitations**: Any caveats or constraints

When comparing multiple studies, explicitly note areas of agreement and disagreement."""

DEVCHAT_SIMPLE_SYSTEM_PROMPT = """You are DevChat, a helpful assistant for 3ie's \
Development Evidence Portal. Provide clear, concise answers based on the retrieved context. \
Always cite your sources."""

# =============================================================================
# QUERY PROCESSING PROMPTS
# =============================================================================

QUERY_CLASSIFICATION_PROMPT = """Classify the following user query into one of these categories:

1. **simple**: Direct factual question about a specific study or concept
   Examples: "What is CCT?", "Who authored the Kenya study?", "When was this published?"

2. **lookup**: Request to find studies matching specific criteria
   Examples: "Find studies on school meals in Africa", "List RCTs on microfinance"

3. **synthesis**: Request to summarize findings across multiple studies
   Examples: "What do studies say about cash transfers?", "Summarize the evidence on deworming"

4. **comparison**: Request to compare findings across studies or interventions
   Examples: "Compare CCTs vs UCTs", "How do effects differ between Africa and Asia?"

5. **methodology**: Question about research methods or study design
   Examples: "What methods are used to evaluate education programs?", "Explain RCT design"

User Query: {query}

Respond with ONLY the category name (simple, lookup, synthesis, comparison, or methodology)."""


QUERY_EXPANSION_PROMPT = """You are a query expansion specialist for academic research on \
international development. Given a user's search query, expand it to improve retrieval.

Your task:
1. Add synonyms and related terms
2. Expand acronyms (CCT → conditional cash transfer)
3. Include domain-specific terminology
4. Add related concepts that might appear in relevant documents

IMPORTANT: 
- Keep the original query intent
- Output should be a single expanded query string (not a list)
- Focus on terms likely to appear in academic papers

Original Query: {query}

Expanded Query:"""


METADATA_EXTRACTION_PROMPT = """Extract ONLY explicitly stated filters from this query.

IMPORTANT: Only extract a filter if the user EXPLICITLY mentions it as a constraint.
- Do NOT infer filters from the topic of the query
- "cash transfers on food security" → NO sector filter (food security is the TOPIC, not a filter)
- "studies in Kenya" → YES, country filter: Kenya
- "RCTs on education" → YES, study_type filter: RCT; but NO sector filter for education (it's the topic)
- "recent studies on health" → YES, year filter (recent = last 3-5 years); but NO sector filter

Filter types:
- **year**: ONLY if user says "recent", "after 2020", "2015-2020", "last 5 years", etc.
- **sector**: ONLY if user says "in the health sector", "education sector studies", etc.
- **country**: ONLY if user explicitly names a country/region as a constraint
- **study_type**: ONLY if user says "RCTs", "systematic reviews", "quasi-experimental", etc.
- **confidence**: ONLY if user says "high quality", "rigorous", "high confidence"

User Query: {query}

Respond in JSON format:
{{
    "year_min": null or integer,
    "year_max": null or integer,
    "sectors": [],
    "countries": [],
    "study_types": [],
    "confidence_level": null
}}

When in doubt, use null/empty. Better to return no filters than incorrect ones."""


# =============================================================================
# SYNTHESIS PROMPTS
# =============================================================================

SYNTHESIS_PROMPT = """Based on the retrieved study context below, answer the user's question.

CONTEXT:
{context}

USER QUESTION: {query}

CRITICAL INSTRUCTIONS:
1. You MUST cite EVERY study provided in the context using [1], [2], [3] etc.
2. Each study number corresponds to its order in the context above
3. When making any claim, cite the specific study(ies) that support it
4. If a study is less relevant, still mention it briefly (e.g., "[2] provides related evidence on X")
5. Synthesize findings across ALL studies, noting patterns and discrepancies
6. Distinguish between strong consensus and mixed evidence
7. Note methodological differences that might explain varying results
8. If context is insufficient, acknowledge this clearly
9. Do NOT include a References section - just cite with [1], [2], etc. inline

IMPORTANT: Every study in the context MUST be cited at least once in your response.

Your response:"""


COMPARISON_PROMPT = """Based on the retrieved study context, compare and contrast the findings.

CONTEXT:
{context}

USER QUESTION: {query}

CRITICAL: You MUST reference ALL studies provided using [1], [2], [3] etc. No study should go unmentioned.

Structure your comparison as:

1. **Areas of Agreement**: Where do studies reach similar conclusions? Cite each: [1], [2], etc.
2. **Areas of Disagreement**: Where do findings diverge? Cite the specific studies.
3. **Possible Explanations**: Why might results differ? (methodology, context, population)
4. **Overall Assessment**: What can we conclude despite the differences?

Use numbered citations like [1], [2], [3] throughout. Every study MUST be cited at least once.
Do NOT include a References section at the end - just cite with [1], [2], etc. inline."""


SIMPLE_ANSWER_PROMPT = """Based on the context provided, give a direct answer to the question.

CONTEXT:
{context}

QUESTION: {query}

IMPORTANT: Cite ALL studies provided using [1], [2], etc. Every study must be mentioned.
Provide a clear, concise answer. Do NOT include a References section at the end."""


# =============================================================================
# CITATION PROMPTS
# =============================================================================

CITATION_FORMAT_PROMPT = """Format the following study information as a proper citation:

Title: {title}
Authors: {authors}
Year: {year}
Source: {source}

Provide the citation in APA format."""


# =============================================================================
# SUGGESTION GENERATION PROMPT
# =============================================================================

SUGGESTION_GENERATION_PROMPT = """Based on the user's research query and the answer provided, generate 3 helpful follow-up query suggestions.

The suggestions should help the user:
1. **Refine** - Narrow down or focus on a specific aspect
2. **Expand** - Explore related topics or broaden the search
3. **Compare** - Compare different approaches, regions, or methodologies

Keep suggestions concise (under 10 words each) and phrase them as questions or commands.

User Query: {query}

Answer Summary: {answer_summary}

Studies Found: {study_count}
Topics Covered: {topics}

Generate exactly 3 follow-up suggestions, one per line. No numbering or bullets."""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_synthesis_prompt(
    query: str,
    context: str,
    query_type: str = "synthesis"
) -> str:
    """
    Get the appropriate synthesis prompt based on query type.
    
    Args:
        query: User's question
        context: Retrieved context
        query_type: Type of query (simple, synthesis, comparison)
    
    Returns:
        Formatted prompt string
    """
    prompts = {
        "simple": SIMPLE_ANSWER_PROMPT,
        "lookup": SYNTHESIS_PROMPT,
        "synthesis": SYNTHESIS_PROMPT,
        "comparison": COMPARISON_PROMPT,
        "methodology": SYNTHESIS_PROMPT,
    }
    
    template = prompts.get(query_type, SYNTHESIS_PROMPT)
    return template.format(query=query, context=context)


def get_system_prompt(query_type: Optional[str] = None) -> str:
    """
    Get the appropriate system prompt.
    
    Args:
        query_type: Type of query (if known)
    
    Returns:
        System prompt string
    """
    if query_type == "simple":
        return DEVCHAT_SIMPLE_SYSTEM_PROMPT
    return DEVCHAT_SYSTEM_PROMPT
