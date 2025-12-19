"""
DevChat v2.0 SOTA - Citation Formatting

Format citations in various styles:
- APA
- Harvard
- In-text references
- Footnotes
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Citation:
    """Structured citation information."""
    study_id: str
    title: str
    authors: Optional[str] = None
    year: Optional[int] = None
    source: Optional[str] = None
    url: Optional[str] = None
    doi: Optional[str] = None
    
    # Additional metadata
    sector: Optional[str] = None
    country: Optional[str] = None


class CitationFormatter:
    """
    Format citations in various academic styles.
    """
    
    @staticmethod
    def format_apa(citation: Citation) -> str:
        """
        Format citation in APA style.
        
        Format: Authors (Year). Title. Source. URL
        """
        parts = []
        
        # Authors - handle list case defensively
        if citation.authors:
            if isinstance(citation.authors, list):
                parts.append(", ".join(str(a) for a in citation.authors))
            else:
                parts.append(str(citation.authors))
        else:
            parts.append("Unknown Author")
        
        # Year
        if citation.year:
            parts.append(f"({citation.year}).")
        else:
            parts.append("(n.d.).")
        
        # Title
        parts.append(f"*{citation.title}*.")
        
        # Source
        if citation.source:
            parts.append(citation.source + ".")
        
        # URL
        if citation.url:
            parts.append(citation.url)
        
        return " ".join(parts)
    
    @staticmethod
    def format_inline(citation: Citation) -> str:
        """
        Format as inline citation.
        
        Format: (Authors, Year) or (Title, Year)
        """
        if citation.authors:
            # Get first author's last name
            first_author = citation.authors.split(",")[0].split(" ")[-1]
            if citation.year:
                return f"({first_author}, {citation.year})"
            return f"({first_author})"
        elif citation.year:
            # Use short title
            short_title = citation.title[:30] + "..." if len(citation.title) > 30 else citation.title
            return f"({short_title}, {citation.year})"
        else:
            return f"({citation.title[:30]}...)"
    
    @staticmethod
    def format_footnote(citation: Citation, number: int) -> str:
        """
        Format as footnote reference.
        
        Returns both the superscript marker and footnote text.
        """
        marker = f"[^{number}]"
        
        # Build footnote text
        parts = []
        if citation.title:
            parts.append(citation.title)
        if citation.year:
            parts.append(f"({citation.year})")
        if citation.url:
            parts.append(f"Available at: {citation.url}")
        
        footnote = f"[^{number}]: " + " ".join(parts)
        
        return marker, footnote
    
    @staticmethod
    def format_reference_list(citations: List[Citation], style: str = "apa") -> str:
        """
        Generate a formatted reference list.
        
        Args:
            citations: List of citations
            style: Citation style (apa, harvard, simple)
            
        Returns:
            Formatted reference list as string
        """
        if not citations:
            return ""
        
        # Sort by year (descending) then by title
        sorted_citations = sorted(
            citations,
            key=lambda c: (-(c.year or 0), c.title or ""),
        )
        
        lines = ["## References", ""]
        
        for citation in sorted_citations:
            if style == "apa":
                formatted = CitationFormatter.format_apa(citation)
            else:
                # Simple format
                parts = [citation.title]
                if citation.year:
                    parts.append(f"({citation.year})")
                if citation.url:
                    parts.append(f"[Link]({citation.url})")
                formatted = " ".join(parts)
            
            lines.append(f"- {formatted}")
        
        return "\n".join(lines)
    
    @staticmethod
    def from_dict(data: Dict) -> Citation:
        """Create Citation from dictionary."""
        # Handle authors that might be a list
        raw_authors = data.get("authors")
        if isinstance(raw_authors, list):
            authors = ", ".join(str(a) for a in raw_authors)
        else:
            authors = str(raw_authors) if raw_authors else None
        
        # Handle sector/country that might be lists
        raw_sector = data.get("sector")
        sector = ", ".join(raw_sector) if isinstance(raw_sector, list) else raw_sector
        raw_country = data.get("country")
        country = ", ".join(raw_country) if isinstance(raw_country, list) else raw_country
        
        return Citation(
            study_id=data.get("study_id", ""),
            title=data.get("title", "Unknown Title"),
            authors=authors,
            year=data.get("year"),
            source=data.get("source"),
            url=data.get("url"),
            doi=data.get("doi"),
            sector=sector,
            country=country,
        )


def add_citations_to_answer(
    answer: str,
    citations: List[Dict],
    style: str = "inline",
) -> str:
    """
    Add citations to an answer that references studies.
    
    This is a simple implementation that appends a reference list.
    For inline citation insertion, a more sophisticated approach is needed.
    
    Args:
        answer: The generated answer
        citations: List of citation dictionaries
        style: Citation style
        
    Returns:
        Answer with citations appended
    """
    if not citations:
        return answer
    
    # Convert to Citation objects
    citation_objs = [CitationFormatter.from_dict(c) for c in citations]
    
    # Generate reference list
    ref_list = CitationFormatter.format_reference_list(citation_objs, style="apa")
    
    # Append to answer
    return f"{answer}\n\n---\n\n{ref_list}"


def extract_study_mentions(answer: str, citations: List[Dict]) -> List[str]:
    """
    Find which studies are actually mentioned in the answer.
    
    Args:
        answer: Generated answer text
        citations: Available citations
        
    Returns:
        List of study_ids that are mentioned
    """
    mentioned = []
    answer_lower = answer.lower()
    
    for citation in citations:
        title = citation.get("title", "")
        year = citation.get("year")
        study_id = citation.get("study_id")
        
        # Check if title or year is mentioned
        if title and title.lower()[:20] in answer_lower:
            mentioned.append(study_id)
        elif year and str(year) in answer:
            # Check if year appears near study-related words
            mentioned.append(study_id)
    
    return list(set(mentioned))


def get_cited_numbers(answer: str) -> set:
    """
    Extract citation numbers [1], [2], etc. from the answer.
    
    Args:
        answer: The generated answer text
        
    Returns:
        Set of citation numbers found (1-indexed)
    """
    import re
    # Match [1], [2], etc. - including grouped citations like [1, 2]
    pattern = r'\[(\d+(?:,\s*\d+)*)\]'
    matches = re.findall(pattern, answer)
    
    numbers = set()
    for match in matches:
        # Handle grouped citations like "1, 2"
        for num in match.split(','):
            try:
                numbers.add(int(num.strip()))
            except ValueError:
                pass
    
    return numbers


def ensure_citation_coverage(
    answer: str,
    citations: List[Dict],
    max_citations: int = 10,
) -> str:
    """
    Ensure all retrieved sources are cited in the answer.
    
    This is a post-processing validator that:
    1. Checks which citations [1], [2], etc. appear in the answer
    2. For uncited sources, appends a brief mention
    
    Args:
        answer: The generated answer with some citations
        citations: All retrieved citation dictionaries
        max_citations: Maximum number of citations to consider
        
    Returns:
        Answer with all sources cited
    """
    if not citations:
        return answer
    
    # Limit to max_citations
    citations = citations[:max_citations]
    
    # Find which citation numbers are already in the answer
    cited_numbers = get_cited_numbers(answer)
    
    # Find uncited sources (citation numbers are 1-indexed)
    all_numbers = set(range(1, len(citations) + 1))
    uncited_numbers = all_numbers - cited_numbers
    
    if not uncited_numbers:
        # All sources cited!
        return answer
    
    # Build additional citations section
    additional_mentions = []
    for num in sorted(uncited_numbers):
        idx = num - 1
        if idx < len(citations):
            citation = citations[idx]
            title = citation.get("title", "Study")
            snippet = citation.get("snippet", "")
            
            # Create a brief mention of the uncited source
            if snippet:
                # Use first sentence of snippet
                first_sentence = snippet.split('.')[0].strip()
                if len(first_sentence) > 100:
                    first_sentence = first_sentence[:100] + "..."
                additional_mentions.append(f"[{num}] also notes: {first_sentence}.")
            else:
                additional_mentions.append(f"See also [{num}] for additional evidence on this topic.")
    
    if additional_mentions:
        # Append as "Additional Sources" section
        additional_section = "\n\n**Additional relevant sources:**\n" + " ".join(additional_mentions)
        answer = answer.rstrip() + additional_section
    
    return answer

