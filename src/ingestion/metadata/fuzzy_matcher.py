"""
DevChat v2.0 SOTA - Fuzzy Matcher

Match bibliography entries to PDF files using fuzzy string matching.
Handles variations in:
- Filename conventions
- Title formatting
- Author name formats
"""

import re
from pathlib import Path
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass
from difflib import SequenceMatcher

from .bibliography import BibliographyEntry
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MatchResult:
    """Result of a fuzzy match attempt."""
    bibliography_entry: BibliographyEntry
    pdf_path: Path
    match_score: float  # 0-1
    match_method: str  # "exact_filename", "fuzzy_title", "author_year", etc.
    confidence: str  # "high", "medium", "low"


class FuzzyMatcher:
    """
    Match bibliography entries to PDF files.
    
    Match strategies (in order of preference):
    1. Exact filename match
    2. Fuzzy filename match
    3. Title in filename
    4. First author + year in filename
    """
    
    def __init__(
        self,
        high_threshold: float = 0.85,
        medium_threshold: float = 0.65,
        low_threshold: float = 0.45,
    ):
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold
        self.low_threshold = low_threshold
    
    def match_entries_to_pdfs(
        self,
        entries: List[BibliographyEntry],
        pdf_paths: List[Path],
    ) -> Tuple[List[MatchResult], List[BibliographyEntry], List[Path]]:
        """
        Match bibliography entries to PDF files.
        
        Args:
            entries: List of bibliography entries
            pdf_paths: List of PDF file paths
            
        Returns:
            Tuple of:
            - matched: List of successful MatchResult
            - unmatched_entries: Entries without PDF match
            - unmatched_pdfs: PDFs without entry match
        """
        matched = []
        matched_entry_indices = set()
        matched_pdf_indices = set()
        
        # Build normalized filename index
        pdf_name_index = {
            self._normalize(p.stem): (i, p) 
            for i, p in enumerate(pdf_paths)
        }
        
        for entry_idx, entry in enumerate(entries):
            best_match: Optional[MatchResult] = None
            
            # Strategy 1: Exact filename match (if entry has pdf_filename)
            if entry.pdf_filename:
                normalized_name = self._normalize(Path(entry.pdf_filename).stem)
                if normalized_name in pdf_name_index:
                    pdf_idx, pdf_path = pdf_name_index[normalized_name]
                    if pdf_idx not in matched_pdf_indices:
                        best_match = MatchResult(
                            bibliography_entry=entry,
                            pdf_path=pdf_path,
                            match_score=1.0,
                            match_method="exact_filename",
                            confidence="high",
                        )
            
            # Strategy 2: Fuzzy filename match
            if not best_match and entry.pdf_filename:
                match = self._find_fuzzy_filename_match(
                    entry.pdf_filename, pdf_paths, matched_pdf_indices
                )
                if match and match[1] >= self.medium_threshold:
                    best_match = MatchResult(
                        bibliography_entry=entry,
                        pdf_path=match[0],
                        match_score=match[1],
                        match_method="fuzzy_filename",
                        confidence=self._score_to_confidence(match[1]),
                    )
            
            # Strategy 3: Title in filename
            if not best_match:
                match = self._find_title_in_filename(
                    entry.title, pdf_paths, matched_pdf_indices
                )
                if match and match[1] >= self.low_threshold:
                    best_match = MatchResult(
                        bibliography_entry=entry,
                        pdf_path=match[0],
                        match_score=match[1],
                        match_method="title_in_filename",
                        confidence=self._score_to_confidence(match[1]),
                    )
            
            # Strategy 4: Author + Year in filename
            if not best_match and entry.authors and entry.year:
                match = self._find_author_year_match(
                    entry.authors, entry.year, pdf_paths, matched_pdf_indices
                )
                if match and match[1] >= self.medium_threshold:
                    best_match = MatchResult(
                        bibliography_entry=entry,
                        pdf_path=match[0],
                        match_score=match[1],
                        match_method="author_year",
                        confidence=self._score_to_confidence(match[1]),
                    )
            
            if best_match:
                matched.append(best_match)
                matched_entry_indices.add(entry_idx)
                matched_pdf_indices.add(pdf_paths.index(best_match.pdf_path))
        
        # Collect unmatched
        unmatched_entries = [
            e for i, e in enumerate(entries) if i not in matched_entry_indices
        ]
        unmatched_pdfs = [
            p for i, p in enumerate(pdf_paths) if i not in matched_pdf_indices
        ]
        
        logger.info(
            f"Matching complete: {len(matched)} matched, "
            f"{len(unmatched_entries)} entries unmatched, "
            f"{len(unmatched_pdfs)} PDFs unmatched"
        )
        
        return matched, unmatched_entries, unmatched_pdfs
    
    def _normalize(self, text: str) -> str:
        """Normalize text for matching."""
        # Lowercase
        text = text.lower()
        # Remove special characters
        text = re.sub(r'[^\w\s]', ' ', text)
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def _similarity(self, a: str, b: str) -> float:
        """Calculate similarity ratio between two strings."""
        return SequenceMatcher(None, a, b).ratio()
    
    def _find_fuzzy_filename_match(
        self,
        filename: str,
        pdf_paths: List[Path],
        exclude_indices: set,
    ) -> Optional[Tuple[Path, float]]:
        """Find best fuzzy filename match."""
        normalized = self._normalize(Path(filename).stem)
        best_path = None
        best_score = 0.0
        
        for i, pdf_path in enumerate(pdf_paths):
            if i in exclude_indices:
                continue
            
            pdf_normalized = self._normalize(pdf_path.stem)
            score = self._similarity(normalized, pdf_normalized)
            
            if score > best_score:
                best_score = score
                best_path = pdf_path
        
        return (best_path, best_score) if best_path else None
    
    def _find_title_in_filename(
        self,
        title: str,
        pdf_paths: List[Path],
        exclude_indices: set,
    ) -> Optional[Tuple[Path, float]]:
        """Find PDF with title in filename."""
        title_normalized = self._normalize(title)
        title_words = set(title_normalized.split())
        
        # Remove common words
        stopwords = {"the", "a", "an", "and", "or", "of", "in", "on", "for", "to", "with"}
        title_words -= stopwords
        
        best_path = None
        best_score = 0.0
        
        for i, pdf_path in enumerate(pdf_paths):
            if i in exclude_indices:
                continue
            
            filename_normalized = self._normalize(pdf_path.stem)
            filename_words = set(filename_normalized.split())
            
            # Calculate word overlap
            if title_words:
                overlap = len(title_words & filename_words) / len(title_words)
            else:
                overlap = 0
            
            # Also check substring match
            substring_score = 0.0
            if len(title_normalized) >= 10:
                # Check if significant part of title appears in filename
                for length in [30, 20, 15, 10]:
                    if len(title_normalized) >= length:
                        chunk = title_normalized[:length]
                        if chunk in filename_normalized:
                            substring_score = length / len(title_normalized)
                            break
            
            score = max(overlap, substring_score)
            
            if score > best_score:
                best_score = score
                best_path = pdf_path
        
        return (best_path, best_score) if best_path else None
    
    def _find_author_year_match(
        self,
        authors: List[str],
        year: int,
        pdf_paths: List[Path],
        exclude_indices: set,
    ) -> Optional[Tuple[Path, float]]:
        """Find PDF matching author + year pattern."""
        if not authors:
            return None
        
        # Get first author's last name
        first_author = authors[0]
        # Handle "First Last" or "Last, First" format
        if "," in first_author:
            last_name = first_author.split(",")[0].strip()
        else:
            parts = first_author.split()
            last_name = parts[-1] if parts else ""
        
        last_name = self._normalize(last_name)
        year_str = str(year)
        
        best_path = None
        best_score = 0.0
        
        for i, pdf_path in enumerate(pdf_paths):
            if i in exclude_indices:
                continue
            
            filename = self._normalize(pdf_path.stem)
            
            # Check for author name
            has_author = last_name in filename
            # Check for year
            has_year = year_str in filename
            
            if has_author and has_year:
                score = 0.9
            elif has_author:
                score = 0.5
            elif has_year:
                score = 0.3
            else:
                score = 0.0
            
            if score > best_score:
                best_score = score
                best_path = pdf_path
        
        return (best_path, best_score) if best_path else None
    
    def _score_to_confidence(self, score: float) -> str:
        """Convert match score to confidence level."""
        if score >= self.high_threshold:
            return "high"
        elif score >= self.medium_threshold:
            return "medium"
        else:
            return "low"


# Convenience function
def match_bibliography_to_pdfs(
    entries: List[BibliographyEntry],
    pdf_directory: Path,
) -> Tuple[List[MatchResult], List[BibliographyEntry], List[Path]]:
    """
    Match bibliography entries to PDFs in a directory.
    
    Args:
        entries: List of BibliographyEntry objects
        pdf_directory: Path to directory containing PDFs
        
    Returns:
        Tuple of (matched, unmatched_entries, unmatched_pdfs)
    """
    pdf_paths = list(pdf_directory.glob("*.pdf"))
    matcher = FuzzyMatcher()
    return matcher.match_entries_to_pdfs(entries, pdf_paths)
