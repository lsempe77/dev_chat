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


def get_cited_indices(answer: str, citations: List[Dict]) -> set:
    """
    Extract which citation indices (0-based) are referenced in the answer.
    
    Detects multiple citation formats:
    1. Bracketed numbers: [1], [2], [1, 2]
    2. Ordinal references: "first study", "second study", "third study"
    3. Study titles mentioned in text
    4. Author names with years: "Smith (2020)"
    
    Args:
        answer: The generated answer text
        citations: List of citation dictionaries
        
    Returns:
        Set of citation indices (0-based) found in answer
    """
    import re
    
    cited_indices = set()
    answer_lower = answer.lower()
    
    # Method 1: Bracketed numbers [1], [2], [1, 2]
    bracket_pattern = r'\[(\d+(?:,\s*\d+)*)\]'
    matches = re.findall(bracket_pattern, answer)
    for match in matches:
        for num in match.split(','):
            try:
                idx = int(num.strip()) - 1  # Convert to 0-based
                if 0 <= idx < len(citations):
                    cited_indices.add(idx)
            except ValueError:
                pass
    
    # Method 2: Ordinal references ("first study", "second study", etc.)
    ordinals = [
        ("first", 0), ("1st", 0),
        ("second", 1), ("2nd", 1),
        ("third", 2), ("3rd", 2),
        ("fourth", 3), ("4th", 3),
        ("fifth", 4), ("5th", 4),
        ("sixth", 5), ("6th", 5),
        ("seventh", 6), ("7th", 6),
        ("eighth", 7), ("8th", 7),
        ("ninth", 8), ("9th", 8),
        ("tenth", 9), ("10th", 9),
    ]
    
    for ordinal, idx in ordinals:
        # Look for patterns like "the first study", "first study shows"
        if re.search(rf'\b{ordinal}\s+(?:study|paper|article|research|evaluation|review)\b', answer_lower):
            if idx < len(citations):
                cited_indices.add(idx)
    
    # Method 3: Title mentions (check if study title appears in answer)
    for idx, citation in enumerate(citations):
        title = citation.get("title", "")
        if title:
            # Check first 30 chars of title (case-insensitive)
            title_start = title.lower()[:30]
            if len(title_start) > 10 and title_start in answer_lower:
                cited_indices.add(idx)
        
        # Method 4: Author + year pattern
        authors = citation.get("authors", "")
        year = citation.get("year")
        if authors and year:
            # Get first author's last name
            if isinstance(authors, list):
                first_author = str(authors[0]) if authors else ""
            else:
                first_author = str(authors).split(",")[0].strip()
            
            # Extract last name (last word)
            last_name = first_author.split()[-1] if first_author.split() else ""
            
            if last_name and len(last_name) > 2:
                # Look for "LastName (Year)" or "LastName, Year"
                author_year_pattern = rf'\b{re.escape(last_name.lower())}\b.*?\b{year}\b'
                if re.search(author_year_pattern, answer_lower):
                    cited_indices.add(idx)
    
    return cited_indices


def ensure_citation_coverage(
    answer: str,
    citations: List[Dict],
    max_citations: int = 10,
) -> str:
    """
    Ensure all retrieved sources are mentioned in the answer.
    
    This post-processor:
    1. Detects which sources are already cited (by [N], ordinals, titles, or author-year)
    2. For truly uncited sources, appends a clean "See also" section
    
    Args:
        answer: The generated answer (may have inline citations)
        citations: All retrieved citation dictionaries
        max_citations: Maximum number of citations to consider
        
    Returns:
        Answer with all sources referenced
    """
    if not citations:
        return answer
    
    # Limit to max_citations
    citations = citations[:max_citations]
    
    # Find which citations are already referenced (0-based indices)
    cited_indices = get_cited_indices(answer, citations)
    
    # Find uncited sources
    all_indices = set(range(len(citations)))
    uncited_indices = all_indices - cited_indices
    
    if not uncited_indices:
        # All sources cited - great!
        return answer
    
    # Build "See also" section for uncited sources
    see_also_items = []
    for idx in sorted(uncited_indices):
        citation = citations[idx]
        title = citation.get("title", "")
        year = citation.get("year", "")
        authors = citation.get("authors", "")
        
        # Format: [N] Author (Year) - Title snippet
        num = idx + 1  # 1-based for display
        
        # Get first author
        if isinstance(authors, list):
            first_author = str(authors[0]).split(",")[0].strip() if authors else ""
        else:
            first_author = str(authors).split(",")[0].strip() if authors else ""
        
        # Get short title
        short_title = title[:50] + "..." if len(title) > 50 else title
        
        if first_author and year:
            see_also_items.append(f"[{num}] {first_author} ({year})")
        elif short_title:
            see_also_items.append(f"[{num}] {short_title}")
        else:
            see_also_items.append(f"[{num}]")
    
    if see_also_items:
        # Append as clean "See also" line
        see_also_text = "\n\n**See also:** " + ", ".join(see_also_items) + "."
        answer = answer.rstrip() + see_also_text
    
    return answer

