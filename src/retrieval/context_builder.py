"""
DevChat v2.0 SOTA - Context Builder

Assembles retrieved results into formatted context for the LLM:
- Parent chunk expansion
- Study grouping
- Citation metadata formatting
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from src.retrieval.hybrid_retriever import RetrievalResult
from src.utils.logging import get_logger

logger = get_logger(__name__)


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
        max_context_length: int = 8000,
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
        
        # Count unique studies
        unique_studies = set(r.study_id for r in results if r.study_id)
        
        return FormattedContext(
            text=context_text,
            num_chunks=len(results),
            num_studies=len(unique_studies),
            citations=citations,
        )
    
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
            sector = meta.get("sector", "")
            country = meta.get("country", "")
            
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
            
            # Combine chunk texts
            chunk_texts = [c.text for c in chunks]
            combined_text = "\n\n".join(chunk_texts)
            
            # Add to sections
            sections.append(f"{header}\n\n{combined_text}")
            
            # Get best snippet from chunks (first 300 chars of first chunk)
            best_snippet = chunks[0].text[:300] if chunks else ""
            
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
            
            if title:
                header = f"[{title}"
                if year:
                    header += f", {year}"
                header += "]"
                chunk_text = f"{header}\n{result.text}"
            else:
                chunk_text = result.text
            
            chunks.append(chunk_text)
            
            # Track citations
            study_id = result.study_id
            if study_id and study_id not in seen_studies:
                seen_studies.add(study_id)
                citations.append({
                    "study_id": study_id,
                    "title": title,
                    "authors": meta.get("authors"),
                    "year": year,
                    "sector": meta.get("sector"),
                    "country": meta.get("country"),
                    "url": meta.get("url"),
                    "doi": meta.get("doi"),
                    "snippet": result.text[:300],
                    "score": result.score,
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
