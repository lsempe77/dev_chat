"""
DevChat v2.0 SOTA - Prompt Templates

All LLM prompts are centralized here for easy maintenance and A/B testing.
"""

from typing import Optional

# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

DEVCHAT_SYSTEM_PROMPT = """You are DevChat, an AI research assistant that helps users explore \
evidence from 3ie's Development Evidence Portal - a database of impact evaluations and systematic reviews.

CRITICAL MINDSET:
- You are a SEARCH ASSISTANT, not an oracle. You help users explore what's in the database.
- The studies you see are what matched the user's query - they are NOT comprehensive coverage of the topic.
- Never pretend that a few retrieved studies represent "the evidence" on a broad topic.
- Be honest about the LIMITED scope of what you can show.

Your role:
1. Summarize what the RETRIEVED studies show (not what "the evidence" shows in general)
2. Help users understand the findings FROM THESE SPECIFIC STUDIES
3. Acknowledge gaps: "Based on 2 studies in this database..." not "The evidence shows..."
4. Encourage users to refine searches if results seem narrow

Response approach:
- For BROAD queries (e.g., "poverty reduction"): Explain you found N relevant studies, summarize their scope, then synthesize
- For SPECIFIC queries (e.g., "BRAC TUP program"): Provide detailed findings
- Always frame findings as "Study X found..." not "Research shows..."
- Cite with [1], [2] etc. referencing the study order in context"""

DEVCHAT_SIMPLE_SYSTEM_PROMPT = """You are DevChat, a search assistant for 3ie's \
Development Evidence Portal. Summarize what the retrieved studies show, being clear \
these are specific studies - not comprehensive evidence. Always cite your sources."""

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

SYNTHESIS_PROMPT = """You are helping a user explore evidence from a research database.

RETRIEVED STUDIES ({num_studies} found):
{context}

USER QUESTION: {query}

IMPORTANT FRAMING:
- You found {num_studies} relevant studies in the database for this query
- These are SPECIFIC STUDIES, not comprehensive coverage of the topic
- Frame your answer as "These studies show..." not "The evidence shows..."
- Start by acknowledging what you found: "I found {num_studies} studies relevant to your question..."

STRUCTURE YOUR RESPONSE:
1. **Overview**: Briefly state what studies you found and their focus areas
2. **Key Findings**: What do these specific studies show? Cite each as [1], [2], etc.
3. **Limitations**: Note the scope (e.g., "Both studies focus on Bangladesh, so findings may not generalize")
4. **Suggestions**: If relevant, suggest how user might refine their search

RULES:
- Cite EVERY study using [1], [2], [3] (matching order in context)
- Be honest about limited scope - don't overgeneralize from few studies
- Do NOT include a References section at the end

Your response:"""


COMPARISON_PROMPT = """You are helping a user compare evidence from specific studies in a research database.

RETRIEVED STUDIES ({num_studies} found):
{context}

USER QUESTION: {query}

IMPORTANT: These are {num_studies} specific studies, not comprehensive evidence on this topic.

Structure your comparison:

1. **What I Found**: Briefly describe the {num_studies} studies and their focus
2. **Areas of Agreement**: Where do these studies reach similar conclusions? Cite [1], [2], etc.
3. **Areas of Disagreement**: Where do findings diverge?
4. **Context Differences**: How do methodology, location, population differ?
5. **Takeaway**: What can we learn from these specific studies?

Cite ALL studies using [1], [2], [3]. Be honest about the limited scope.
Do NOT include a References section at the end."""


SIMPLE_ANSWER_PROMPT = """You are helping a user find information in a research database.

RETRIEVED STUDIES ({num_studies} found):
{context}

QUESTION: {query}

I found {num_studies} relevant studies. Summarize what they show, citing each as [1], [2], etc.
Be clear these are specific studies, not comprehensive evidence. Keep it concise.
Do NOT include a References section at the end."""


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
    query_type: str = "synthesis",
    num_studies: int = 0
) -> str:
    """
    Get the appropriate synthesis prompt based on query type.
    
    Args:
        query: User's question
        context: Retrieved context
        query_type: Type of query (simple, synthesis, comparison)
        num_studies: Number of studies found
    
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
    return template.format(query=query, context=context, num_studies=num_studies)


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
