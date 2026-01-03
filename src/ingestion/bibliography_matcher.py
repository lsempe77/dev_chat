"""
Bibliography Matching Service

Matches imported bibliography entries (RIS/BibTeX/CSV) to existing PDF documents.
Uses multiple strategies for matching:
1. DOI matching (most reliable)
2. Title fuzzy matching (>85% similarity)
3. Author+Year combo
4. Filename pattern (author_year.pdf)
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional
from enum import Enum


class MatchMethod(str, Enum):
    """Method used to match bibliography entry to document."""
    DOI = "doi"
    TITLE = "title"
    AUTHOR_YEAR = "author_year"
    FILENAME = "filename"
    MANUAL = "manual"
    NONE = "none"


@dataclass
class BibliographyEntry:
    """Parsed bibliography entry from RIS/BibTeX/CSV."""
    id: str  # Unique identifier from source
    title: str
    authors: list[str]
    year: Optional[int]
    doi: Optional[str]
    journal: Optional[str] = None
    abstract: Optional[str] = None
    keywords: Optional[list[str]] = None
    source_format: str = "unknown"  # ris, bibtex, csv
    raw_data: Optional[dict] = None  # Original parsed data
    
    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []
        if self.raw_data is None:
            self.raw_data = {}


@dataclass
class MatchResult:
    """Result of matching a bibliography entry to a document."""
    entry: BibliographyEntry
    document_id: Optional[str]
    confidence: float  # 0.0 to 1.0
    method: MatchMethod
    match_details: str  # Human-readable explanation


def normalize_doi(doi: Optional[str]) -> Optional[str]:
    """Normalize DOI for comparison."""
    if not doi:
        return None
    
    # Remove common prefixes
    doi = doi.strip().lower()
    doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi)
    doi = re.sub(r'^doi:\s*', '', doi)
    
    return doi if doi else None


def normalize_title(title: str) -> str:
    """Normalize title for comparison."""
    if not title:
        return ""
    
    # Lowercase, remove punctuation, normalize whitespace
    title = title.lower()
    title = re.sub(r'[^\w\s]', ' ', title)
    title = re.sub(r'\s+', ' ', title).strip()
    
    return title


def title_similarity(title1: str, title2: str) -> float:
    """Calculate similarity between two titles (0.0 to 1.0)."""
    t1 = normalize_title(title1)
    t2 = normalize_title(title2)
    
    if not t1 or not t2:
        return 0.0
    
    return SequenceMatcher(None, t1, t2).ratio()


def extract_author_year_from_filename(filename: str) -> tuple[Optional[str], Optional[int]]:
    """
    Extract author and year from common filename patterns.
    
    Patterns:
    - smith2020.pdf
    - Smith_2020.pdf
    - smith-et-al-2020.pdf
    - Smith et al 2020.pdf
    """
    if not filename:
        return None, None
    
    # Remove extension
    name = re.sub(r'\.[^.]+$', '', filename)
    
    # Try to find a 4-digit year
    year_match = re.search(r'(19|20)\d{2}', name)
    year = int(year_match.group()) if year_match else None
    
    # Extract author (text before year or first separator)
    author = None
    if year_match:
        before_year = name[:year_match.start()]
    else:
        before_year = name
    
    # Clean up author name
    author = re.sub(r'[-_\s]+(et[\s_-]*al)?[-_\s]*$', '', before_year, flags=re.IGNORECASE)
    author = re.sub(r'[-_]', ' ', author).strip()
    
    return author.lower() if author else None, year


def normalize_author_name(name: str) -> str:
    """Normalize author name for comparison."""
    if not name:
        return ""
    
    # Get last name (after comma or last word)
    if ',' in name:
        last_name = name.split(',')[0].strip()
    else:
        parts = name.split()
        last_name = parts[-1] if parts else ""
    
    return last_name.lower()


def match_by_doi(
    entry: BibliographyEntry,
    documents: list[dict]
) -> Optional[MatchResult]:
    """Match by DOI (highest confidence)."""
    entry_doi = normalize_doi(entry.doi)
    if not entry_doi:
        return None
    
    for doc in documents:
        doc_doi = normalize_doi(doc.get('metadata', {}).get('doi'))
        if doc_doi and doc_doi == entry_doi:
            return MatchResult(
                entry=entry,
                document_id=doc['id'],
                confidence=1.0,
                method=MatchMethod.DOI,
                match_details=f"DOI match: {entry_doi}"
            )
    
    return None


def match_by_title(
    entry: BibliographyEntry,
    documents: list[dict],
    threshold: float = 0.85
) -> Optional[MatchResult]:
    """Match by title similarity."""
    if not entry.title:
        return None
    
    best_match = None
    best_score = 0.0
    
    for doc in documents:
        doc_title = doc.get('metadata', {}).get('title', '') or doc.get('original_filename', '')
        score = title_similarity(entry.title, doc_title)
        
        if score > best_score and score >= threshold:
            best_score = score
            best_match = doc
    
    if best_match:
        return MatchResult(
            entry=entry,
            document_id=best_match['id'],
            confidence=best_score,
            method=MatchMethod.TITLE,
            match_details=f"Title similarity: {best_score:.1%}"
        )
    
    return None


def match_by_author_year(
    entry: BibliographyEntry,
    documents: list[dict]
) -> Optional[MatchResult]:
    """Match by first author last name + year."""
    if not entry.authors or not entry.year:
        return None
    
    first_author = normalize_author_name(entry.authors[0])
    if not first_author:
        return None
    
    for doc in documents:
        doc_meta = doc.get('metadata', {})
        doc_year = doc_meta.get('year')
        doc_authors = doc_meta.get('authors', '')
        
        # Extract first author from doc
        if isinstance(doc_authors, str):
            doc_first = normalize_author_name(doc_authors.split(',')[0] if doc_authors else '')
        elif isinstance(doc_authors, list) and doc_authors:
            doc_first = normalize_author_name(doc_authors[0])
        else:
            continue
        
        # Check year match (allow ±1 year for edge cases)
        year_matches = doc_year and abs(int(doc_year) - entry.year) <= 1
        author_matches = doc_first and first_author in doc_first or doc_first in first_author
        
        if year_matches and author_matches:
            return MatchResult(
                entry=entry,
                document_id=doc['id'],
                confidence=0.75,
                method=MatchMethod.AUTHOR_YEAR,
                match_details=f"Author+Year: {first_author} ({entry.year})"
            )
    
    return None


def match_by_filename(
    entry: BibliographyEntry,
    documents: list[dict]
) -> Optional[MatchResult]:
    """Match by filename pattern (author_year.pdf)."""
    if not entry.authors or not entry.year:
        return None
    
    first_author = normalize_author_name(entry.authors[0])
    if not first_author:
        return None
    
    for doc in documents:
        filename = doc.get('filename', '') or doc.get('original_filename', '')
        file_author, file_year = extract_author_year_from_filename(filename)
        
        if not file_author or not file_year:
            continue
        
        # Check matches
        author_match = first_author in file_author or file_author in first_author
        year_match = abs(file_year - entry.year) <= 1
        
        if author_match and year_match:
            return MatchResult(
                entry=entry,
                document_id=doc['id'],
                confidence=0.65,
                method=MatchMethod.FILENAME,
                match_details=f"Filename pattern: {filename}"
            )
    
    return None


def match_entry(
    entry: BibliographyEntry,
    documents: list[dict]
) -> MatchResult:
    """
    Try all matching strategies in order of reliability.
    Returns the best match or a 'no match' result.
    """
    # Try strategies in order of reliability
    strategies = [
        match_by_doi,
        match_by_title,
        match_by_author_year,
        match_by_filename,
    ]
    
    for strategy in strategies:
        result = strategy(entry, documents)
        if result:
            return result
    
    # No match found
    return MatchResult(
        entry=entry,
        document_id=None,
        confidence=0.0,
        method=MatchMethod.NONE,
        match_details="No automatic match found"
    )


def match_entries(
    entries: list[BibliographyEntry],
    documents: list[dict]
) -> tuple[list[MatchResult], list[MatchResult]]:
    """
    Match all entries to documents.
    Returns (matched, unmatched) tuples.
    """
    matched = []
    unmatched = []
    
    for entry in entries:
        result = match_entry(entry, documents)
        if result.document_id:
            matched.append(result)
        else:
            unmatched.append(result)
    
    return matched, unmatched
