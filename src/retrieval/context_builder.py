"""
DevChat v2.0 SOTA - Context Builder

Assembles retrieved results into formatted context for the LLM:
- Parent chunk expansion
- Study grouping
- Citation metadata formatting
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from src.retrieval.hybrid_retriever import RetrievalResult
from src.utils.logging import get_logger

logger = get_logger(__name__)


def is_meaningful_text(text: str, min_words: int = 10) -> bool:
    """
    Check if text is meaningful content vs headers/metadata.
    
    Args:
        text: Text to check
        min_words: Minimum word count to be considered meaningful
        
    Returns:
        True if text appears to be meaningful content
    """
    if not text:
        return False
    
    # Clean and count words
    words = text.split()
    if len(words) < min_words:
        return False
    
    # Check for patterns that indicate headers/metadata
    text_lower = text.lower()
    header_patterns = [
        "working paper",
        "discussion paper",
        "abstract",
        "keywords:",
        "jel codes:",
        "table of contents",
        "acknowledgments",
        "references",
        "appendix",
        "this version:",
        "department of",
        "university",
    ]
    
    # If text starts with or is mostly these patterns, skip it
    first_50_chars = text_lower[:50]
    for pattern in header_patterns:
        if pattern in first_50_chars:
            return False
    
    return True


def get_best_snippet(chunks: list, max_length: int = 300) -> str:
    """
    Get the best meaningful snippet from a list of chunks.
    
    Prefers chunks with actual content over headers/metadata.
    
    Args:
        chunks: List of RetrievalResult objects
        max_length: Maximum length of snippet
        
    Returns:
        Best snippet text
    """
    if not chunks:
        return ""
    
    # Try to find a meaningful chunk
    for chunk in chunks:
        text = chunk.text if isinstance(chunk.text, str) else str(chunk.text)
        if is_meaningful_text(text):
            return clean_text_for_display(text, max_length)
    
    # Fall back to first chunk if none are meaningful
    first_text = chunks[0].text if isinstance(chunks[0].text, str) else str(chunks[0].text)
    return clean_text_for_display(first_text, max_length)


def clean_text_for_display(text: str, max_length: int = 300) -> str:
    """
    Clean text for display by removing HTML tags, excessive whitespace,
    and other artifacts.
    
    Args:
        text: Raw text that may contain HTML or artifacts
        max_length: Maximum length of returned snippet
        
    Returns:
        Clean text suitable for display
    """
    if not text:
        return ""
    
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', ' ', text)
    
    # Remove HTML entities
    clean = re.sub(r'&[a-zA-Z]+;', ' ', clean)
    clean = re.sub(r'&#\d+;', ' ', clean)
    
    # Remove markdown-style formatting artifacts
    clean = re.sub(r'\|+', ' ', clean)  # Table pipes
    clean = re.sub(r'-{3,}', ' ', clean)  # Horizontal rules
    clean = re.sub(r'\*{2,}', ' ', clean)  # Bold markers
    
    # Normalize whitespace
    clean = re.sub(r'\s+', ' ', clean)
    clean = clean.strip()
    
    # Truncate to max length at word boundary
    if len(clean) > max_length:
        # Find last space before max_length
        truncate_at = clean.rfind(' ', 0, max_length)
        if truncate_at > max_length * 0.5:  # At least half the length
            clean = clean[:truncate_at] + "..."
        else:
            clean = clean[:max_length] + "..."
    
    return clean


@dataclass
class FormattedContext:
    """Formatted context ready for LLM."""
    text: str
    num_chunks: int
    num_studies: int
    citations: List[Dict]
    
    def __str__(self) -> str:
        return self.text


class ContextBuilder:
    """
    Build formatted context from retrieval results.
    
    Features:
    - Expand to parent chunks for more context
    - Group results by study
    - Format with metadata headers
    - Generate citation list
    """
    
    def __init__(
        self,
        max_context_length: int = 16000,  # Increased from 8000 to allow more studies
        use_parent_expansion: bool = True,
        group_by_study: bool = True,
    ):
        self.max_context_length = max_context_length
        self.use_parent_expansion = use_parent_expansion
        self.group_by_study = group_by_study
    
    def build(self, results: List[RetrievalResult]) -> FormattedContext:
        """
        Build formatted context from retrieval results.
        
        Args:
            results: Retrieved and reranked results
            
        Returns:
            FormattedContext with text and metadata
        """
        if not results:
            return FormattedContext(
                text="No relevant studies found.",
                num_chunks=0,
                num_studies=0,
                citations=[],
            )
        
        # Optionally expand to parent chunks
        if self.use_parent_expansion:
            results = self._expand_to_parents(results)
        
        # Group by study if enabled
        if self.group_by_study:
            context_text, citations = self._build_grouped_context(results)
        else:
            context_text, citations = self._build_flat_context(results)
        
        # Truncate if needed
        if len(context_text) > self.max_context_length:
            context_text = self._smart_truncate(context_text)
            # Filter citations to only include studies still present in truncated text
            citations = self._filter_citations_by_context(citations, context_text)
        
        # Count unique studies (based on what's actually in the context after truncation)
        num_studies = len(citations)
        
        return FormattedContext(
            text=context_text,
            num_chunks=len(results),
            num_studies=num_studies,
            citations=citations,
        )
    
    def _filter_citations_by_context(
        self,
        citations: List[Dict],
        context_text: str,
    ) -> List[Dict]:
        """
        Filter citations to only include those whose [N] marker is in the context.
        
        This ensures citations match what's actually in the text after truncation.
        """
        import re
        
        # Find all [N] markers in the context
        present_markers = set(re.findall(r'\[(\d+)\]', context_text))
        
        # Filter and re-number citations
        filtered = []
        for i, citation in enumerate(citations, start=1):
            if str(i) in present_markers:
                filtered.append(citation)
        
        if len(filtered) < len(citations):
            logger.debug(
                f"Truncation removed {len(citations) - len(filtered)} citations "
                f"(kept {len(filtered)}/{len(citations)})"
            )
        
        return filtered
    
    def _expand_to_parents(
        self,
        results: List[RetrievalResult],
    ) -> List[RetrievalResult]:
        """Replace child chunks with parent chunks when available."""
        expanded = []
        seen_parents = set()
        
        for result in results:
            parent_text = result.parent_text
            parent_id = result.metadata.get("parent_id")
            
            if parent_text and parent_id:
                # Use parent if not already included
                if parent_id not in seen_parents:
                    seen_parents.add(parent_id)
                    # Create new result with parent text
                    expanded.append(RetrievalResult(
                        node_id=parent_id,
                        text=parent_text,
                        score=result.score,
                        metadata=result.metadata,
                    ))
            else:
                # Keep original chunk
                expanded.append(result)
        
        logger.debug(
            f"Parent expansion: {len(results)} chunks → {len(expanded)} chunks"
        )
        return expanded
    
    def _build_grouped_context(
        self,
        results: List[RetrievalResult],
    ) -> tuple[str, List[Dict]]:
        """Build context grouped by study."""
        # Group by study
        by_study: Dict[str, List[RetrievalResult]] = {}
        for result in results:
            study_id = result.study_id or "unknown"
            if study_id not in by_study:
                by_study[study_id] = []
            by_study[study_id].append(result)
        
        # Build formatted text
        sections = []
        citations = []
        
        # Use enumerate to assign citation numbers
        for citation_num, (study_id, chunks) in enumerate(by_study.items(), start=1):
            # Get study metadata from first chunk
            meta = chunks[0].metadata
            title = meta.get("title", f"Study {study_id}")
            year = meta.get("year", "")
            
            # Handle sector/country that might be lists
            raw_sector = meta.get("sector", "")
            sector = ", ".join(raw_sector) if isinstance(raw_sector, list) else str(raw_sector) if raw_sector else ""
            raw_country = meta.get("country", "")
            country = ", ".join(raw_country) if isinstance(raw_country, list) else str(raw_country) if raw_country else ""
            
            # Build header with citation number [1], [2], etc.
            header_parts = [f"[{citation_num}] **{title}**"]
            if year:
                header_parts.append(f"({year})")
            
            subheader_parts = []
            if sector:
                subheader_parts.append(f"Sector: {sector}")
            if country:
                subheader_parts.append(f"Country: {country}")
            
            header = " ".join(header_parts)
            if subheader_parts:
                header += f"\n*{', '.join(subheader_parts)}*"
            
            # Combine chunk texts - ensure each is a string
            chunk_texts = [c.text if isinstance(c.text, str) else str(c.text) for c in chunks]
            combined_text = "\n\n".join(chunk_texts)
            
            # Add to sections
            sections.append(f"{header}\n\n{combined_text}")
            
            # Get best MEANINGFUL snippet from chunks (skip headers/metadata)
            best_snippet = get_best_snippet(chunks, max_length=300)
            
            # Get page info from first chunk (all chunks from same study may span pages)
            page_start = meta.get("page_start")
            page_end = meta.get("page_end")
            pages = meta.get("pages", [])
            
            # If multiple chunks, get the range
            if len(chunks) > 1:
                all_pages = set()
                for c in chunks:
                    chunk_pages = c.metadata.get("pages", [])
                    if chunk_pages:
                        all_pages.update(chunk_pages)
                    elif c.metadata.get("page_start"):
                        all_pages.add(c.metadata.get("page_start"))
                if all_pages:
                    pages = sorted(all_pages)
                    page_start = min(all_pages)
                    page_end = max(all_pages)
            
            # Add citation
            citations.append({
                "study_id": study_id,
                "title": title,
                "authors": meta.get("authors"),
                "year": year,
                "sector": sector,
                "country": country,
                "url": meta.get("url"),
                "doi": meta.get("doi"),
                "snippet": best_snippet,
                "score": chunks[0].score if chunks else 0.0,
                "page_start": page_start,
                "page_end": page_end,
                "pages": pages,
            })
        
        # Join with separators
        context_text = "\n\n---\n\n".join(sections)
        
        return context_text, citations
    
    def _build_flat_context(
        self,
        results: List[RetrievalResult],
    ) -> tuple[str, List[Dict]]:
        """Build flat context without grouping."""
        chunks = []
        citations = []
        seen_studies = set()
        
        for result in results:
            # Format chunk with minimal header
            meta = result.metadata
            title = meta.get("title", "")
            year = meta.get("year", "")
            
            # Ensure text is a string
            result_text = result.text if isinstance(result.text, str) else str(result.text)
            
            if title:
                header = f"[{title}"
                if year:
                    header += f", {year}"
                header += "]"
                chunk_text = f"{header}\n{result_text}"
            else:
                chunk_text = result_text
            
            chunks.append(chunk_text)
            
            # Track citations
            study_id = result.study_id
            if study_id and study_id not in seen_studies:
                seen_studies.add(study_id)
                
                # Handle sector/country that might be lists
                raw_sector = meta.get("sector")
                sector = ", ".join(raw_sector) if isinstance(raw_sector, list) else str(raw_sector) if raw_sector else ""
                raw_country = meta.get("country")
                country = ", ".join(raw_country) if isinstance(raw_country, list) else str(raw_country) if raw_country else ""
                
                citations.append({
                    "study_id": study_id,
                    "title": title,
                    "authors": meta.get("authors"),
                    "year": year,
                    "sector": sector,
                    "country": country,
                    "url": meta.get("url"),
                    "doi": meta.get("doi"),
                    "snippet": clean_text_for_display(result.text, 300),
                    "score": result.score,
                    "page_start": meta.get("page_start"),
                    "page_end": meta.get("page_end"),
                    "pages": meta.get("pages", []),
                })
        
        context_text = "\n\n".join(chunks)
        return context_text, citations
    
    def _smart_truncate(self, text: str) -> str:
        """
        Truncate text intelligently at sentence boundaries.
        
        Preserves complete sentences and adds truncation notice.
        """
        if len(text) <= self.max_context_length:
            return text
        
        # Find a good break point
        truncate_at = self.max_context_length - 100  # Leave room for notice
        
        # Try to break at paragraph
        last_para = text.rfind("\n\n", 0, truncate_at)
        if last_para > truncate_at * 0.7:
            truncate_at = last_para
        else:
            # Try to break at sentence
            for punct in [". ", ".\n", "! ", "? "]:
                last_sent = text.rfind(punct, 0, truncate_at)
                if last_sent > truncate_at * 0.7:
                    truncate_at = last_sent + 1
                    break
        
        truncated = text[:truncate_at].strip()
        truncated += "\n\n[Context truncated due to length...]"
        
        return truncated


def build_context_for_query(
    results: List[RetrievalResult],
    query_type: str = "synthesis",
) -> FormattedContext:
    """
    Build context optimized for query type.
    
    Args:
        results: Retrieved results
        query_type: Type of query (simple, synthesis, comparison)
        
    Returns:
        Formatted context
    """
    # Adjust settings based on query type
    if query_type == "simple":
        builder = ContextBuilder(
            max_context_length=4000,
            use_parent_expansion=False,
            group_by_study=False,
        )
    elif query_type == "comparison":
        builder = ContextBuilder(
            max_context_length=12000,
            use_parent_expansion=True,
            group_by_study=True,
        )
    else:
        builder = ContextBuilder()
    
    return builder.build(results)
