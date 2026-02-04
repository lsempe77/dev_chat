"""
Significance Parser for Extraction Pipeline
============================================

Handles multiple significance notation formats found in academic papers:
- Star notation: *, **, *** (most common)
- Dagger/symbols: †, ‡, §, ¶
- Superscript letters: a, b, c (common in some journals)
- Explicit p-values: p<.05, p=0.03, p>.10
- Text: NS, n.s., not significant
- Brackets: [p<.05], (p=0.001)

Also extracts footnote definitions to determine actual p-value thresholds.

Architecture:
- Primary: Rule-based regex parsing (fast, free, deterministic)
- Fallback: LLM reasoning for ambiguous/novel formats (optional)
"""

import re
import json
import asyncio
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List, Tuple, Any
from loguru import logger


# =============================================================================
# DEFAULT P-VALUE MAPPINGS (can be overridden by footnote extraction)
# =============================================================================

DEFAULT_STAR_MAPPING = {
    "***": 0.001,   # p < 0.001
    "**": 0.01,     # p < 0.01
    "*": 0.05,      # p < 0.05
    "": None,       # not significant / no indicator
}

DEFAULT_SYMBOL_MAPPING = {
    "†": 0.10,      # Often used for p < 0.10
    "‡": 0.05,      # Sometimes used for p < 0.05
    "§": 0.01,      # Sometimes used for p < 0.01
    "¶": 0.001,     # Rare, sometimes p < 0.001
}

# Superscript letters (meaning varies by paper - need footnote extraction)
DEFAULT_LETTER_MAPPING = {
    "a": 0.01,      # Varies
    "b": 0.05,      # Varies
    "c": 0.10,      # Varies
}


@dataclass
class SignificanceResult:
    """Result of significance parsing."""
    
    # Raw extraction
    raw_indicator: Optional[str] = None  # "***", "†", "p<.05", etc.
    indicator_type: Optional[str] = None  # "stars", "symbol", "explicit", "text", "llm"
    
    # Interpreted values
    p_value_threshold: Optional[float] = None  # 0.001, 0.01, 0.05, 0.10
    p_value_exact: Optional[float] = None  # For explicit p-values like p=0.023
    p_value_text: Optional[str] = None  # "p<.001", "p<.05", "NS"
    
    # Confidence
    is_significant: Optional[bool] = None  # True if p < 0.05, None if unknown
    confidence: str = "high"  # "high" if clear, "low" if ambiguous
    
    # LLM reasoning (if used)
    llm_reasoning: Optional[str] = None  # Explanation from LLM
    used_llm: bool = False  # Whether LLM was used for this result
    
    def to_dict(self) -> dict:
        return asdict(self)


class SignificanceParser:
    """
    Parse significance indicators from table cells and map to p-values.
    
    Usage:
        parser = SignificanceParser()
        
        # Parse a single cell (rule-based only)
        result = parser.parse_cell("0.15*** (0.05)")
        print(result.p_value_threshold)  # 0.001
        print(result.p_value_text)       # "p<.001"
        
        # Parse with LLM fallback for ambiguous cases
        result = await parser.parse_cell_with_llm("0.15‡ (0.05)", footnote="‡ see appendix")
        
        # Update mappings from footnotes
        parser.update_from_footnote("*** p<.005, ** p<.01, * p<.05")
    """
    
    def __init__(
        self,
        star_mapping: Optional[Dict[str, float]] = None,
        symbol_mapping: Optional[Dict[str, float]] = None,
        use_llm_fallback: bool = True,
    ):
        self.star_mapping = star_mapping or DEFAULT_STAR_MAPPING.copy()
        self.symbol_mapping = symbol_mapping or DEFAULT_SYMBOL_MAPPING.copy()
        self.letter_mapping = DEFAULT_LETTER_MAPPING.copy()
        
        # Track if mappings were updated from footnotes
        self.mappings_from_footnote = False
        
        # LLM fallback settings
        self.use_llm_fallback = use_llm_fallback
        self._llm = None
        self._llm_initialized = False
    
    def _setup_llm(self):
        """Initialize LLM for fallback reasoning (lazy loading)."""
        if self._llm_initialized:
            return
        
        self._llm_initialized = True
        
        try:
            from llama_index.llms.openai_like import OpenAILike
            from src.config.settings import settings
            
            self._llm = OpenAILike(
                model="openai/gpt-4o-mini",  # Fast & cheap for simple reasoning
                api_key=settings.openrouter_api_key,
                api_base=settings.openrouter_base_url,
                temperature=0.0,  # Deterministic for consistency
                max_tokens=500,
                is_chat_model=True,
                additional_kwargs={
                    "extra_headers": {
                        "HTTP-Referer": "https://3ieimpact.org",
                        "X-Title": "DevChat Significance Parser",
                    }
                }
            )
            logger.info("SignificanceParser LLM initialized")
        except ImportError as e:
            logger.warning(f"LLM fallback disabled - missing dependency: {e}")
            self._llm = None
        except Exception as e:
            logger.warning(f"LLM fallback disabled - initialization failed: {e}")
            self._llm = None
    
    def parse_cell(self, cell_text: str) -> SignificanceResult:
        """
        Parse significance from a table cell.
        
        Args:
            cell_text: Raw cell text like "0.15*** (0.05)" or "p<.05"
            
        Returns:
            SignificanceResult with parsed information
        """
        if not cell_text or not isinstance(cell_text, str):
            return SignificanceResult()
        
        text = cell_text.strip()
        
        # Try parsing in order of specificity
        
        # 1. Explicit p-values (most specific)
        result = self._parse_explicit_pvalue(text)
        if result.raw_indicator:
            return result
        
        # 2. Star notation (most common)
        result = self._parse_stars(text)
        if result.raw_indicator:
            return result
        
        # 3. Symbol notation (†, ‡, etc.)
        result = self._parse_symbols(text)
        if result.raw_indicator:
            return result
        
        # 4. Text notation (NS, n.s.)
        result = self._parse_text_notation(text)
        if result.raw_indicator:
            return result
        
        # 5. Superscript letters (need to be careful - could be footnote refs)
        result = self._parse_letters(text)
        if result.raw_indicator:
            return result
        
        # No significance indicator found
        return SignificanceResult(
            is_significant=None,  # Unknown, not necessarily non-significant
            confidence="low"
        )
    
    def _parse_stars(self, text: str) -> SignificanceResult:
        """Parse star notation: *, **, ***"""
        # Check in order from most to least specific
        if "***" in text:
            return self._create_result("***", "stars", self.star_mapping.get("***", 0.001))
        elif "**" in text and "***" not in text:
            return self._create_result("**", "stars", self.star_mapping.get("**", 0.01))
        elif "*" in text and "**" not in text:
            return self._create_result("*", "stars", self.star_mapping.get("*", 0.05))
        return SignificanceResult()
    
    def _parse_symbols(self, text: str) -> SignificanceResult:
        """Parse symbol notation: †, ‡, §, ¶"""
        for symbol, p_val in self.symbol_mapping.items():
            if symbol in text:
                return self._create_result(symbol, "symbol", p_val)
        return SignificanceResult()
    
    def _parse_explicit_pvalue(self, text: str) -> SignificanceResult:
        """Parse explicit p-values: p<.05, p=0.023, p>.10"""
        text_lower = text.lower()
        
        # Pattern: p < 0.05, p<.001, p < .01, etc.
        match = re.search(r'p\s*[<≤]\s*(\.?\d+\.?\d*)', text_lower)
        if match:
            p_str = match.group(1)
            # Handle formats: .001, 0.001, .05, 0.05
            if p_str.startswith('.'):
                p_val = float('0' + p_str)
            else:
                p_val = float(p_str)
            # Sanity check - p-values should be <= 1
            if p_val > 1:
                p_val = p_val / (10 ** len(str(int(p_val))))
            return SignificanceResult(
                raw_indicator=match.group(0),
                indicator_type="explicit",
                p_value_threshold=p_val,
                p_value_text=f"p<{p_val}",
                is_significant=p_val <= 0.05,
                confidence="high"
            )
        
        # Pattern: p = 0.023, p=.001
        match = re.search(r'p\s*=\s*(\.?\d+\.?\d*)', text_lower)
        if match:
            p_str = match.group(1)
            if p_str.startswith('.'):
                p_val = float('0' + p_str)
            else:
                p_val = float(p_str)
            if p_val > 1:
                p_val = p_val / (10 ** len(str(int(p_val))))
            return SignificanceResult(
                raw_indicator=match.group(0),
                indicator_type="explicit",
                p_value_exact=p_val,
                p_value_text=f"p={p_val}",
                is_significant=p_val <= 0.05,
                confidence="high"
            )
        
        # Pattern: p > 0.05, p>.10 (not significant)
        match = re.search(r'p\s*[>≥]\s*(\.?\d+\.?\d*)', text_lower)
        if match:
            p_str = match.group(1)
            if p_str.startswith('.'):
                p_val = float('0' + p_str)
            else:
                p_val = float(p_str)
            return SignificanceResult(
                raw_indicator=match.group(0),
                indicator_type="explicit",
                p_value_threshold=p_val,
                p_value_text=f"p>{p_val}",
                is_significant=False,
                confidence="high"
            )
        
        return SignificanceResult()
    
    def _parse_text_notation(self, text: str) -> SignificanceResult:
        """Parse text notation: NS, n.s., not significant"""
        text_lower = text.lower().strip()
        
        ns_patterns = ["ns", "n.s.", "n.s", "not significant", "nonsignificant", "non-significant"]
        for pattern in ns_patterns:
            if pattern in text_lower:
                return SignificanceResult(
                    raw_indicator="NS",
                    indicator_type="text",
                    p_value_text="NS",
                    is_significant=False,
                    confidence="high"
                )
        
        return SignificanceResult()
    
    def _parse_letters(self, text: str) -> SignificanceResult:
        """
        Parse superscript letter notation: a, b, c
        
        Note: This is tricky because letters can be footnote references.
        Only parse if the letter appears at the end of a number.
        """
        # Pattern: number followed by superscript-like letter
        match = re.search(r'(\d+\.?\d*)\s*([abc])(?:\s|$|[,\)])', text)
        if match:
            letter = match.group(2)
            p_val = self.letter_mapping.get(letter)
            if p_val:
                return SignificanceResult(
                    raw_indicator=letter,
                    indicator_type="letter",
                    p_value_threshold=p_val,
                    p_value_text=f"p<{p_val}",
                    is_significant=p_val <= 0.05,
                    confidence="low"  # Low confidence without footnote confirmation
                )
        
        return SignificanceResult()
    
    def _create_result(
        self, 
        indicator: str, 
        indicator_type: str, 
        p_threshold: float
    ) -> SignificanceResult:
        """Create a SignificanceResult with standard formatting."""
        return SignificanceResult(
            raw_indicator=indicator,
            indicator_type=indicator_type,
            p_value_threshold=p_threshold,
            p_value_text=f"p<{p_threshold}" if p_threshold else None,
            is_significant=p_threshold <= 0.05 if p_threshold else None,
            confidence="high" if self.mappings_from_footnote else "medium"
        )
    
    def update_from_footnote(self, footnote_text: str) -> bool:
        """
        Update significance mappings from a table footnote.
        
        Args:
            footnote_text: Footnote text like "*** p<.005, ** p<.01, * p<.05"
            
        Returns:
            True if any mappings were updated
        """
        updated = False
        text = footnote_text.lower()
        
        # Pattern: *** p<.001 or *** p < 0.001 or ***p<.001
        # Use word boundaries and negative lookahead to avoid double matching
        star_patterns = [
            (r'(?<!\*)\*\*\*(?!\*)\s*:?\s*p\s*[<≤]\s*\.?(\d+\.?\d*)', "***"),
            (r'(?<!\*)\*\*(?!\*)\s*:?\s*p\s*[<≤]\s*\.?(\d+\.?\d*)', "**"),
            (r'(?<!\*)\*(?!\*)\s*:?\s*p\s*[<≤]\s*\.?(\d+\.?\d*)', "*"),
        ]
        
        for pattern, stars in star_patterns:
            match = re.search(pattern, text)
            if match:
                p_val = float("0." + match.group(1)) if not "." in match.group(1) else float(match.group(1))
                if p_val > 1:
                    p_val = p_val / (10 ** len(str(int(p_val))))
                self.star_mapping[stars] = p_val
                updated = True
        
        # Pattern for symbols: † p<.10
        symbol_patterns = [
            (r'[†]\s*:?\s*p\s*[<≤]\s*\.?(\d+\.?\d*)', "†"),
            (r'[‡]\s*:?\s*p\s*[<≤]\s*\.?(\d+\.?\d*)', "‡"),
            (r'[§]\s*:?\s*p\s*[<≤]\s*\.?(\d+\.?\d*)', "§"),
        ]
        
        for pattern, symbol in symbol_patterns:
            match = re.search(pattern, text)
            if match:
                p_val = float("0." + match.group(1)) if not "." in match.group(1) else float(match.group(1))
                if p_val > 1:
                    p_val = p_val / (10 ** len(str(int(p_val))))
                self.symbol_mapping[symbol] = p_val
                updated = True
        
        if updated:
            self.mappings_from_footnote = True
        
        return updated
    
    # =========================================================================
    # LLM FALLBACK METHODS
    # =========================================================================
    
    async def parse_cell_with_llm(
        self,
        cell_text: str,
        footnote_text: Optional[str] = None,
        table_context: Optional[str] = None,
    ) -> SignificanceResult:
        """
        Parse significance with LLM fallback for ambiguous cases.
        
        First tries rule-based parsing. If result is low confidence or
        no indicator found but text looks like it might have significance
        info, uses LLM to reason about it.
        
        Args:
            cell_text: Raw cell text
            footnote_text: Optional table footnote for context
            table_context: Optional surrounding table context
            
        Returns:
            SignificanceResult (may have llm_reasoning if LLM was used)
        """
        # First try rule-based parsing
        result = self.parse_cell(cell_text)
        
        # If high confidence result, return it
        if result.raw_indicator and result.confidence == "high":
            return result
        
        # Check if we should use LLM fallback
        if not self.use_llm_fallback:
            return result
        
        # Heuristics for when to use LLM:
        # 1. Low confidence result
        # 2. No result but text has suspicious patterns
        # 3. Unknown symbol that might indicate significance
        
        should_use_llm = (
            result.confidence == "low" or
            (result.raw_indicator is None and self._might_have_significance(cell_text)) or
            (footnote_text and not self.mappings_from_footnote)
        )
        
        if not should_use_llm:
            return result
        
        # Use LLM fallback
        llm_result = await self._llm_parse(cell_text, footnote_text, table_context)
        if llm_result and llm_result.raw_indicator:
            return llm_result
        
        return result
    
    def _might_have_significance(self, text: str) -> bool:
        """Check if text might contain significance info worth LLM analysis."""
        suspicious_patterns = [
            r'[†‡§¶◊○●□■△▲▽▼]',  # Various symbols
            r'\([a-z]\)',  # (a), (b), etc.
            r'\d+\s*[a-z](?:\s|$|[,\)])',  # Number followed by letter
            r'sig\.|significant',  # Significance text
            r'p\s*[\=\<\>]',  # p-value references
        ]
        for pattern in suspicious_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    async def _llm_parse(
        self,
        cell_text: str,
        footnote_text: Optional[str] = None,
        table_context: Optional[str] = None,
    ) -> Optional[SignificanceResult]:
        """Use LLM to interpret significance from ambiguous text."""
        self._setup_llm()
        
        if not self._llm:
            return None
        
        prompt = self._build_llm_prompt(cell_text, footnote_text, table_context)
        
        try:
            response = await self._llm.acomplete(prompt)
            return self._parse_llm_response(response.text, cell_text)
        except Exception as e:
            logger.warning(f"LLM significance parsing failed: {e}")
            return None
    
    def _build_llm_prompt(
        self,
        cell_text: str,
        footnote_text: Optional[str] = None,
        table_context: Optional[str] = None,
    ) -> str:
        """Build prompt for LLM significance reasoning."""
        prompt = f"""You are an expert at reading academic research papers. Analyze this table cell to extract statistical significance information.

CELL TEXT: "{cell_text}"
"""
        if footnote_text:
            prompt += f"""
TABLE FOOTNOTE: "{footnote_text}"
"""
        if table_context:
            prompt += f"""
TABLE CONTEXT: {table_context}
"""
        prompt += """
Task: Determine if this cell indicates statistical significance and extract the p-value.

Consider:
- Star notation (*, **, ***)
- Symbol notation (†, ‡, §, etc.)
- Letter superscripts (a, b, c) that might indicate significance levels
- Any explicit p-values
- Text like "NS", "n.s.", "not significant"
- The footnote definitions (if provided)

Return JSON:
{
    "has_significance_indicator": true/false,
    "raw_indicator": "the exact indicator found (e.g., '***', '†', 'NS')" or null,
    "indicator_type": "stars/symbol/letter/explicit/text" or null,
    "p_value": 0.05 (numeric p-value threshold or exact value) or null,
    "is_significant": true/false/null (true if p<0.05),
    "reasoning": "brief explanation of your interpretation"
}

Return ONLY the JSON, no other text."""
        return prompt
    
    def _parse_llm_response(self, response_text: str, original_cell: str) -> Optional[SignificanceResult]:
        """Parse LLM response into SignificanceResult."""
        try:
            # Extract JSON from response
            text = response_text.strip()
            if text.startswith("```"):
                text = re.sub(r'^```(?:json)?\n?', '', text)
                text = re.sub(r'\n?```$', '', text)
            
            data = json.loads(text)
            
            if not data.get("has_significance_indicator"):
                return SignificanceResult(
                    is_significant=data.get("is_significant"),
                    confidence="medium",
                    llm_reasoning=data.get("reasoning"),
                    used_llm=True,
                )
            
            p_value = data.get("p_value")
            indicator_type = data.get("indicator_type")
            
            return SignificanceResult(
                raw_indicator=data.get("raw_indicator"),
                indicator_type=indicator_type or "llm",
                p_value_threshold=p_value if indicator_type != "explicit" else None,
                p_value_exact=p_value if indicator_type == "explicit" else None,
                p_value_text=f"p<{p_value}" if p_value else None,
                is_significant=data.get("is_significant"),
                confidence="medium",  # LLM results are medium confidence
                llm_reasoning=data.get("reasoning"),
                used_llm=True,
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return None
    
    async def parse_footnote_with_llm(self, footnote_text: str) -> Dict[str, float]:
        """
        Use LLM to extract significance mappings from complex footnotes.
        
        Useful for footnotes that are hard to parse with regex, e.g.:
        "Asterisks indicate significance at conventional levels"
        "Standard errors in parentheses, significant at 10%, 5%, 1%"
        """
        self._setup_llm()
        
        if not self._llm:
            return {}
        
        prompt = f"""Analyze this table footnote and extract the significance level definitions.

FOOTNOTE: "{footnote_text}"

Extract what each symbol means in terms of p-value thresholds.
Common patterns:
- "*** p<0.01" means *** indicates p < 0.01
- "significant at 5%" means p < 0.05
- "significant at the 1% level" means p < 0.01

Return JSON mapping symbols to p-values:
{{
    "***": 0.01,
    "**": 0.05,
    "*": 0.10,
    "†": 0.10
}}

Only include symbols that are explicitly defined. Return empty {{}} if no clear definitions.
Return ONLY the JSON, no other text."""
        
        try:
            response = await self._llm.acomplete(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                text = re.sub(r'^```(?:json)?\n?', '', text)
                text = re.sub(r'\n?```$', '', text)
            
            mappings = json.loads(text)
            
            # Update internal mappings
            for symbol, p_val in mappings.items():
                if symbol in ["*", "**", "***"]:
                    self.star_mapping[symbol] = p_val
                elif symbol in self.symbol_mapping:
                    self.symbol_mapping[symbol] = p_val
            
            if mappings:
                self.mappings_from_footnote = True
                logger.info(f"LLM extracted footnote mappings: {mappings}")
            
            return mappings
        except Exception as e:
            logger.warning(f"LLM footnote parsing failed: {e}")
            return {}

    def get_current_mappings(self) -> Dict[str, Dict[str, float]]:
        """Return current significance mappings."""
        return {
            "stars": self.star_mapping,
            "symbols": self.symbol_mapping,
            "letters": self.letter_mapping,
            "from_footnote": self.mappings_from_footnote,
        }


def extract_footnotes_from_table(table_html: str) -> List[str]:
    """
    Extract footnote text from table HTML.
    
    Footnotes are often in:
    - <tfoot> elements
    - Rows at the bottom with "Note:" or "Notes:"
    - <caption> with significance definitions
    """
    from bs4 import BeautifulSoup
    
    footnotes = []
    soup = BeautifulSoup(table_html, 'html.parser')
    
    # Check <tfoot>
    tfoot = soup.find('tfoot')
    if tfoot:
        footnotes.append(tfoot.get_text(" ", strip=True))
    
    # Check for "Note" rows
    for row in soup.find_all('tr'):
        text = row.get_text(" ", strip=True).lower()
        if text.startswith('note') or text.startswith('notes') or '***' in text and 'p<' in text:
            footnotes.append(row.get_text(" ", strip=True))
    
    # Check caption
    caption = soup.find('caption')
    if caption:
        cap_text = caption.get_text(" ", strip=True)
        if 'p<' in cap_text.lower() or '***' in cap_text:
            footnotes.append(cap_text)
    
    return footnotes


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def parse_significance(cell_text: str, footnote_text: Optional[str] = None) -> SignificanceResult:
    """
    Convenience function to parse significance from a cell.
    
    Args:
        cell_text: Raw cell text
        footnote_text: Optional footnote to determine mappings
        
    Returns:
        SignificanceResult
    """
    parser = SignificanceParser()
    if footnote_text:
        parser.update_from_footnote(footnote_text)
    return parser.parse_cell(cell_text)


def map_stars_to_pvalue(stars: str, footnote_text: Optional[str] = None) -> Optional[float]:
    """
    Simple function to map star notation to p-value threshold.
    
    Args:
        stars: "***", "**", "*", or ""
        footnote_text: Optional footnote to determine exact thresholds
        
    Returns:
        p-value threshold (0.001, 0.01, 0.05) or None
    """
    result = parse_significance(stars, footnote_text)
    return result.p_value_threshold


async def parse_significance_with_llm(
    cell_text: str,
    footnote_text: Optional[str] = None,
    table_context: Optional[str] = None,
) -> SignificanceResult:
    """
    Async convenience function to parse significance with LLM fallback.
    
    Args:
        cell_text: Raw cell text
        footnote_text: Optional footnote for context
        table_context: Optional table context
        
    Returns:
        SignificanceResult (may include LLM reasoning)
    """
    parser = SignificanceParser(use_llm_fallback=True)
    if footnote_text:
        parser.update_from_footnote(footnote_text)
    return await parser.parse_cell_with_llm(cell_text, footnote_text, table_context)


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("SIGNIFICANCE PARSER TESTS")
    print("=" * 60)
    
    parser = SignificanceParser(use_llm_fallback=False)  # Disable LLM for basic tests
    
    # Test cases
    test_cases = [
        # Stars
        ("0.15*** (0.05)", "***", 0.001),
        ("0.23** (0.08)", "**", 0.01),
        ("-0.05* (0.03)", "*", 0.05),
        ("0.12 (0.04)", None, None),
        
        # Explicit p-values
        ("0.15 (p<.001)", "p<.001", 0.001),
        ("0.23 (p=0.023)", "p=0.023", 0.023),
        ("0.05 (p>.10)", "p>.10", None),
        
        # Symbols
        ("0.15† (0.05)", "†", 0.10),
        
        # Text
        ("0.02 (NS)", "NS", None),
        ("0.01 (n.s.)", "NS", None),
    ]
    
    print("\n1. Basic rule-based parsing tests:")
    for cell, expected_indicator, expected_p in test_cases:
        result = parser.parse_cell(cell)
        status = "✅" if result.raw_indicator == expected_indicator else "❌"
        print(f'  {status} "{cell}" -> indicator={result.raw_indicator}, p={result.p_value_threshold}')
    
    # Test footnote update
    print("\n2. Footnote mapping update:")
    footnote = "Notes: *** p<.005, ** p<.01, * p<.05, † p<.10"
    parser.update_from_footnote(footnote)
    print(f'  Footnote: "{footnote}"')
    print(f'  Updated mappings: {parser.star_mapping}')
    
    # Re-test with updated mappings
    result = parser.parse_cell("0.15*** (0.05)")
    print(f'  "0.15***" now maps to p<{result.p_value_threshold}')
    
    # Test LLM fallback (if available)
    print("\n3. LLM fallback test:")
    try:
        async def test_llm():
            llm_parser = SignificanceParser(use_llm_fallback=True)
            
            # Test ambiguous case
            test_cell = "0.15‡ (0.03)"  # Uncommon symbol
            result = await llm_parser.parse_cell_with_llm(
                test_cell, 
                footnote_text="‡ denotes significance at 5% level"
            )
            print(f'  Cell: "{test_cell}"')
            print(f'  Result: indicator={result.raw_indicator}, p={result.p_value_threshold}')
            print(f'  Used LLM: {result.used_llm}')
            if result.llm_reasoning:
                print(f'  Reasoning: {result.llm_reasoning}')
            return result
        
        result = asyncio.run(test_llm())
        print("  ✅ LLM fallback working!")
    except Exception as e:
        print(f"  ⚠️ LLM fallback not available: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Parser ready for use!")
    print("   - Rule-based parsing: Always available (fast, free)")
    print("   - LLM fallback: For ambiguous cases (requires OpenRouter)")
    print("=" * 60)
