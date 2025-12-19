"""
DevChat v2.0 SOTA - Metadata Resolver

Orchestrates metadata resolution from multiple sources:
1. DOI extraction from PDF
2. CrossRef lookup (authoritative)
3. OpenAlex lookup (rich metadata + concepts)
4. LLM extraction (fallback for gaps)

Priority: CrossRef > OpenAlex > LLM
"""

import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum

from .doi_extractor import DOIExtractor
from .crossref_client import CrossRefClient, CrossRefWork
from .openalex_client import OpenAlexClient, OpenAlexWork
from src.utils.logging import get_logger

logger = get_logger(__name__)


class MetadataSource(str, Enum):
    """Source of metadata."""
    CROSSREF = "crossref"
    OPENALEX = "openalex"
    LLM = "llm"
    USER = "user"
    BIBLIOGRAPHY = "bibliography"
    UNKNOWN = "unknown"


class ResolvedMetadata(BaseModel):
    """
    Unified metadata from all sources.
    
    Includes confidence scores and source tracking.
    """
    
    # Core bibliographic fields
    doi: Optional[str] = None
    title: str = "Unknown Title"
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    journal: Optional[str] = None
    publisher: Optional[str] = None
    abstract: Optional[str] = None
    url: Optional[str] = None
    
    # Extended metadata
    keywords: List[str] = Field(default_factory=list)
    cited_by_count: Optional[int] = None
    is_open_access: bool = False
    open_access_url: Optional[str] = None
    type: Optional[str] = None  # article, book-chapter, etc.
    
    # Development-specific fields (from LLM or OpenAlex)
    countries: List[str] = Field(default_factory=list)
    regions: List[str] = Field(default_factory=list)
    sectors: List[str] = Field(default_factory=list)
    study_type: Optional[str] = None  # RCT, quasi-experimental, systematic-review
    intervention_type: Optional[str] = None
    sdgs: List[str] = Field(default_factory=list)  # Sustainable Development Goals
    
    # Source tracking
    primary_source: MetadataSource = MetadataSource.UNKNOWN
    sources_used: List[MetadataSource] = Field(default_factory=list)
    confidence: float = 0.0  # 0-1, based on source quality
    
    # Flags for review
    needs_review: bool = False
    review_reasons: List[str] = Field(default_factory=list)
    
    # Original filename (for linking back)
    pdf_filename: Optional[str] = None
    
    def to_qdrant_payload(self) -> Dict[str, Any]:
        """Convert to Qdrant payload format."""
        return {
            "doi": self.doi,
            "title": self.title,
            "authors": ", ".join(self.authors) if self.authors else None,
            "year": self.year,
            "journal": self.journal,
            "abstract": self.abstract,
            "url": self.url,
            "country": self.countries[0] if self.countries else None,
            "countries": self.countries,
            "sector": self.sectors[0] if self.sectors else None,
            "sectors": self.sectors,
            "study_type": self.study_type,
            "intervention_type": self.intervention_type,
            "cited_by_count": self.cited_by_count,
            "is_open_access": self.is_open_access,
            "metadata_source": self.primary_source.value,
            "metadata_confidence": self.confidence,
            "pdf_name": self.pdf_filename,
        }


class MetadataResolver:
    """
    Resolve metadata for documents from multiple sources.
    
    Resolution flow:
    1. Extract DOI from PDF
    2. If DOI found: CrossRef → OpenAlex for enrichment
    3. If no DOI: LLM extracts title/author → OpenAlex search
    4. LLM fills domain-specific gaps (country, sector, study_type)
    """
    
    def __init__(
        self,
        crossref_email: Optional[str] = None,
        openalex_email: Optional[str] = None,
    ):
        self.doi_extractor = DOIExtractor()
        self.crossref = CrossRefClient(email=crossref_email)
        self.openalex = OpenAlexClient(email=openalex_email)
    
    async def resolve_from_pdf(
        self,
        pdf_path: Path,
        extracted_text: Optional[str] = None,
        fill_gaps_with_llm: bool = True,
    ) -> ResolvedMetadata:
        """
        Resolve metadata for a PDF document.
        
        Args:
            pdf_path: Path to PDF file
            extracted_text: Optional pre-extracted text (first pages)
            fill_gaps_with_llm: Whether to use LLM for domain-specific fields
            
        Returns:
            ResolvedMetadata with all available fields
        """
        result = ResolvedMetadata(pdf_filename=pdf_path.name)
        
        # Step 1: Extract DOI
        logger.info(f"Resolving metadata for: {pdf_path.name}")
        doi = self.doi_extractor.extract_from_pdf(pdf_path)
        
        if doi:
            result.doi = doi
            logger.info(f"Found DOI: {doi}")
            
            # Step 2a: CrossRef lookup
            crossref_result = await self.crossref.get_by_doi(doi)
            if crossref_result:
                self._merge_crossref(result, crossref_result)
            
            # Step 2b: OpenAlex for enrichment (concepts, SDGs, etc.)
            openalex_result = await self.openalex.get_by_doi(doi)
            if openalex_result:
                self._merge_openalex(result, openalex_result)
        
        else:
            logger.warning(f"No DOI found, will try title search")
            result.needs_review = True
            result.review_reasons.append("No DOI found in PDF")
            
            # Step 3: LLM extraction + OpenAlex search
            # TODO: Implement LLM title/author extraction
            # For now, mark as needing manual entry
            
        # Step 4: Fill domain-specific gaps with LLM
        if fill_gaps_with_llm and self._has_gaps(result):
            # TODO: Implement LLM gap filling
            pass
        
        # Calculate confidence
        result.confidence = self._calculate_confidence(result)
        
        # Check if needs review
        if result.confidence < 0.5:
            result.needs_review = True
            if "Low confidence" not in result.review_reasons:
                result.review_reasons.append("Low confidence score")
        
        logger.info(f"Resolved: {result.title[:50]}... (confidence: {result.confidence:.2f})")
        
        return result
    
    async def resolve_from_doi(self, doi: str) -> ResolvedMetadata:
        """
        Resolve metadata for a known DOI.
        
        Args:
            doi: DOI string
            
        Returns:
            ResolvedMetadata
        """
        result = ResolvedMetadata(doi=doi)
        
        # Parallel lookup
        crossref_task = self.crossref.get_by_doi(doi)
        openalex_task = self.openalex.get_by_doi(doi)
        
        crossref_result, openalex_result = await asyncio.gather(
            crossref_task, openalex_task
        )
        
        if crossref_result:
            self._merge_crossref(result, crossref_result)
        
        if openalex_result:
            self._merge_openalex(result, openalex_result)
        
        result.confidence = self._calculate_confidence(result)
        
        return result
    
    async def resolve_batch_dois(self, dois: List[str]) -> List[ResolvedMetadata]:
        """
        Resolve metadata for multiple DOIs efficiently.
        
        Args:
            dois: List of DOI strings
            
        Returns:
            List of ResolvedMetadata
        """
        tasks = [self.resolve_from_doi(doi) for doi in dois]
        return await asyncio.gather(*tasks)
    
    async def search_by_title(
        self,
        title: str,
        author: Optional[str] = None,
        year: Optional[int] = None,
    ) -> Optional[ResolvedMetadata]:
        """
        Search for a work by title/author when DOI is unknown.
        
        Args:
            title: Work title
            author: First author (optional)
            year: Publication year (optional)
            
        Returns:
            ResolvedMetadata if found, None otherwise
        """
        # Try OpenAlex first (better fuzzy matching)
        openalex_result = await self.openalex.search_by_title_author(title, author, year)
        
        if openalex_result:
            result = ResolvedMetadata()
            self._merge_openalex(result, openalex_result)
            
            # If we got a DOI, enrich from CrossRef
            if result.doi:
                crossref_result = await self.crossref.get_by_doi(result.doi)
                if crossref_result:
                    self._merge_crossref(result, crossref_result)
            
            result.confidence = self._calculate_confidence(result)
            return result
        
        # Fallback to CrossRef search
        crossref_results = await self.crossref.search_by_title(title, author, rows=3)
        if crossref_results:
            result = ResolvedMetadata()
            self._merge_crossref(result, crossref_results[0])
            result.needs_review = True
            result.review_reasons.append("Found via title search - verify match")
            result.confidence = self._calculate_confidence(result) * 0.8  # Reduce confidence
            return result
        
        return None
    
    def _merge_crossref(self, result: ResolvedMetadata, crossref: CrossRefWork) -> None:
        """Merge CrossRef data into result."""
        result.doi = result.doi or crossref.doi
        result.title = crossref.title or result.title
        result.authors = crossref.authors or result.authors
        result.year = crossref.year or result.year
        result.journal = crossref.journal or result.journal
        result.publisher = crossref.publisher or result.publisher
        result.abstract = result.abstract or crossref.abstract
        result.url = result.url or crossref.url
        result.cited_by_count = crossref.cited_by_count or result.cited_by_count
        result.type = crossref.type or result.type
        
        if crossref.is_open_access:
            result.is_open_access = True
        
        if crossref.subject:
            result.keywords.extend(crossref.subject)
        
        result.primary_source = MetadataSource.CROSSREF
        if MetadataSource.CROSSREF not in result.sources_used:
            result.sources_used.append(MetadataSource.CROSSREF)
    
    def _merge_openalex(self, result: ResolvedMetadata, openalex: OpenAlexWork) -> None:
        """Merge OpenAlex data into result (enrichment, don't overwrite)."""
        # Only fill gaps, don't overwrite CrossRef data
        result.doi = result.doi or openalex.doi
        result.title = result.title if result.title != "Unknown Title" else openalex.title
        result.authors = result.authors or openalex.authors
        result.year = result.year or openalex.year
        result.journal = result.journal or openalex.journal
        result.publisher = result.publisher or openalex.publisher
        result.abstract = result.abstract or openalex.abstract
        result.url = result.url or openalex.url
        result.cited_by_count = result.cited_by_count or openalex.cited_by_count
        result.type = result.type or openalex.type
        
        # OpenAlex-specific enrichment
        if openalex.is_open_access:
            result.is_open_access = True
        if openalex.open_access_url:
            result.open_access_url = openalex.open_access_url
        
        if openalex.concepts:
            for concept in openalex.concepts[:5]:
                if concept.get("name") and concept["name"] not in result.keywords:
                    result.keywords.append(concept["name"])
        
        if openalex.countries:
            result.countries = list(set(result.countries + openalex.countries))
        
        if openalex.sdgs:
            result.sdgs = list(set(result.sdgs + openalex.sdgs))
        
        if result.primary_source == MetadataSource.UNKNOWN:
            result.primary_source = MetadataSource.OPENALEX
        
        if MetadataSource.OPENALEX not in result.sources_used:
            result.sources_used.append(MetadataSource.OPENALEX)
    
    def _has_gaps(self, result: ResolvedMetadata) -> bool:
        """Check if result has domain-specific gaps to fill."""
        return (
            not result.countries or
            not result.sectors or
            not result.study_type
        )
    
    def _calculate_confidence(self, result: ResolvedMetadata) -> float:
        """
        Calculate confidence score based on data completeness and source.
        
        Returns:
            Float 0-1
        """
        score = 0.0
        
        # Source quality
        if MetadataSource.CROSSREF in result.sources_used:
            score += 0.3
        if MetadataSource.OPENALEX in result.sources_used:
            score += 0.2
        if MetadataSource.BIBLIOGRAPHY in result.sources_used:
            score += 0.25
        if MetadataSource.USER in result.sources_used:
            score += 0.35  # User-verified is highest
        
        # Field completeness
        if result.doi:
            score += 0.1
        if result.title != "Unknown Title":
            score += 0.1
        if result.authors:
            score += 0.1
        if result.year:
            score += 0.05
        if result.abstract:
            score += 0.05
        
        # Domain fields (bonus)
        if result.countries:
            score += 0.05
        if result.study_type:
            score += 0.05
        
        return min(1.0, score)


# Convenience function
async def resolve_pdf_metadata(pdf_path: Path) -> ResolvedMetadata:
    """Resolve metadata for a PDF file."""
    resolver = MetadataResolver()
    return await resolver.resolve_from_pdf(pdf_path)
