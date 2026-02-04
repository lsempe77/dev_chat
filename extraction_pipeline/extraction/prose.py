"""
Prose and Figure Extraction
===========================

Extract treatment effects from prose text and figure captions.
Used as fallback when tables don't yield data.
"""

import re
import json
from typing import Dict, List, Any

from ..core.llm_client import call_llm


def extract_effects_from_prose(doc: dict, study_id: str) -> List[Dict[str, Any]]:
    """
    Extract treatment effects mentioned in prose text.
    
    Used when:
    1. No tables are available (MineRU failure, figures-only papers)
    2. Tables extracted but want to validate/enrich
    3. Key outcomes mentioned only in abstract/conclusion
    
    Extracts patterns like:
    - "increased by X% (SE=Y, p<Z)"
    - "coefficient of X (Y standard errors)"
    - "significant effect of X percentage points"
    - "reduced by X units (95% CI: [A, B])"
    
    Args:
        doc: MineRU JSON document
        study_id: Study identifier
    
    Returns:
        List of effect dictionaries with standardized fields
    """
    content = doc.get('content', '')
    
    # Focus on results-rich sections
    sections_to_search = []
    
    # Look for section markers
    results_pattern = r'(?:^|\n)(?:#+\s*)?(?:results?|findings?|impacts?|effects?)[\s:]*\n(.*?)(?=\n(?:#+\s*)?(?:discussion|conclusion|reference|appendix)|$)'
    abstract_pattern = r'(?:^|\n)(?:#+\s*)?abstract[\s:]*\n(.*?)(?=\n(?:#+\s*)?(?:introduction|background|keywords)|$)'
    conclusion_pattern = r'(?:^|\n)(?:#+\s*)?(?:conclusion|discussion)[\s:]*\n(.*?)(?=\n(?:#+\s*)?(?:reference|appendix|acknowledgment)|$)'
    
    for pattern, section_name in [(abstract_pattern, 'abstract'), 
                                   (results_pattern, 'results'),
                                   (conclusion_pattern, 'conclusion')]:
        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
        if match:
            sections_to_search.append((section_name, match.group(1)[:10000]))
    
    # If no sections found, use first 20k chars
    if not sections_to_search:
        sections_to_search.append(('full_text', content[:20000]))
    
    # Combine sections for LLM
    combined_text = "\n\n".join([f"[{name.upper()}]\n{text[:5000]}" for name, text in sections_to_search])
    
    prompt = f"""Extract ALL treatment effect estimates from this research paper text.

TEXT:
{combined_text[:12000]}

For each effect mentioned, extract:
1. outcome_name: What was measured (e.g., "income", "test scores", "employment rate")
2. treatment_arm: Which treatment group (e.g., "treatment", "cash transfer", "training program") 
3. coefficient: The point estimate (number)
4. standard_error: SE if mentioned (number)
5. p_value: P-value if mentioned (number like 0.05)
6. significance: Stars or significance level (*, **, ***, or "significant at X%")
7. ci_lower: Lower confidence interval bound if mentioned
8. ci_upper: Upper confidence interval bound if mentioned
9. effect_type: "percentage_points", "percent_change", "absolute_units", "standard_deviations"
10. source_sentence: The exact sentence containing this effect

Return as JSON array. Example:
[
  {{
    "outcome_name": "monthly income",
    "treatment_arm": "cash transfer",
    "coefficient": 150.5,
    "standard_error": 45.2,
    "p_value": 0.001,
    "significance": "***",
    "ci_lower": 61.9,
    "ci_upper": 239.1,
    "effect_type": "absolute_units",
    "source_sentence": "Cash transfers increased monthly income by $150.50 (SE=45.2, p<0.001)"
  }}
]

Only include effects with numeric coefficients. Return empty array [] if no effects found.
Return ONLY the JSON array, no other text."""

    result = call_llm(prompt, max_tokens=2000)
    
    # Parse LLM response
    effects = []
    try:
        # Clean up response - find JSON array
        json_match = re.search(r'\[.*\]', result, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, list):
                for effect in parsed:
                    effect['study_id'] = study_id
                    effect['source_type'] = 'prose'
                    effects.append(effect)
    except (json.JSONDecodeError, TypeError) as e:
        print(f"  [WARN] Failed to parse prose effects: {e}")
    
    return effects


def extract_effects_from_figures(doc: dict, study_id: str) -> List[Dict[str, Any]]:
    """
    Extract treatment effects from figure captions and surrounding text.
    
    Used when:
    1. Paper has results in figures/charts instead of tables
    2. Learning briefs, policy briefs with graphical results
    3. Papers where MineRU extracted figures but no tables
    
    Args:
        doc: MineRU JSON document
        study_id: Study identifier
    
    Returns:
        List of effect dictionaries with standardized fields
    """
    content = doc.get('content', '')
    
    # Find figure references and their surrounding context
    figure_contexts = []
    
    # Pattern for markdown images with figure captions
    fig_pattern = r'!\[[^\]]*\]\([^)]+\)\s*\n?(Figure\s*\d*[a-z]?[:\.]?\s*[^\n]+(?:\n(?![#\n]|\!\[)[^\n]+)*)'
    
    matches = list(re.finditer(fig_pattern, content, re.IGNORECASE))
    
    if not matches:
        # Try alternative: just find "Figure X:" patterns
        fig_pattern2 = r'(Figure\s*\d+[a-z]?[:\.]?\s*[^\n]+(?:\n(?![#\n]|\!\[)[^\n]+){0,10})'
        matches = list(re.finditer(fig_pattern2, content, re.IGNORECASE))
    
    for match in matches:
        # Get context: 500 chars before and after
        start = max(0, match.start() - 500)
        end = min(len(content), match.end() + 500)
        context = content[start:end]
        figure_contexts.append(context)
    
    if not figure_contexts:
        return []
    
    # Combine figure contexts
    combined_figures = "\n\n---FIGURE---\n\n".join(figure_contexts[:10])  # Limit to 10 figures
    
    prompt = f"""Extract treatment effect estimates from these figure descriptions and captions.

These are figures from an impact evaluation paper. The figures show treatment effects graphically.
Extract any quantitative information about effects that is mentioned in the captions, notes, or surrounding text.

FIGURE CONTEXTS:
{combined_figures[:10000]}

For each effect mentioned, extract:
1. outcome_name: What outcome was measured
2. treatment_arm: Which treatment (e.g., "poultry package", "cash transfer")
3. coefficient: The point estimate if given as a number
4. standard_error: SE if mentioned
5. p_value: P-value if mentioned (e.g., 0.05, 0.01)
6. significance: Significance level (*, **, ***, "significant", "not significant")
7. ci_lower: Lower CI bound if mentioned
8. ci_upper: Upper CI bound if mentioned  
9. effect_direction: "positive", "negative", "null" (based on description if no number)
10. effect_description: Brief description of the effect (e.g., "18 percentage point increase")
11. figure_reference: Which figure this is from (e.g., "Figure 2")

Return as JSON array. Include effects even if only qualitative (e.g., "significant positive effect").
For qualitative effects without numbers, set coefficient to null but include effect_direction and effect_description.

Example:
[
  {{
    "outcome_name": "poultry ownership",
    "treatment_arm": "poultry package",
    "coefficient": 0.40,
    "standard_error": null,
    "p_value": 0.01,
    "significance": "***",
    "ci_lower": null,
    "ci_upper": null,
    "effect_direction": "positive",
    "effect_description": "40 percentage point increase in poultry ownership",
    "figure_reference": "Figure 2"
  }}
]

Return ONLY the JSON array."""

    result = call_llm(prompt, max_tokens=2500)
    
    # Parse LLM response
    effects = []
    try:
        json_match = re.search(r'\[.*\]', result, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, list):
                for effect in parsed:
                    effect['study_id'] = study_id
                    effect['source_type'] = 'figure'
                    effects.append(effect)
    except (json.JSONDecodeError, TypeError) as e:
        print(f"  [WARN] Failed to parse figure effects: {e}")
    
    return effects


__all__ = [
    'extract_effects_from_prose',
    'extract_effects_from_figures',
]
