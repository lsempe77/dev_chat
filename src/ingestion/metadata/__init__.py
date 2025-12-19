"""
DevChat v2.0 SOTA - Metadata Resolution Pipeline

Smart metadata extraction from multiple sources:
1. DOI extraction from PDF
2. CrossRef/OpenAlex API lookup
3. LLM-based gap filling for domain-specific fields
4. Bibliography import (RIS/BibTeX/CSV)
5. Fuzzy matching of PDFs to bibliography entries
"""

from .doi_extractor import DOIExtractor, extract_doi
from .crossref_client import CrossRefClient, CrossRefWork, lookup_doi
from .openalex_client import OpenAlexClient, OpenAlexWork, search_openalex
from .llm_extractor import (
    LLMMetadataExtractor,
    ExtractedBibliographic,
    ExtractedDomainFields,
    extract_title_from_pdf_text,
    extract_domain_fields,
)
from .bibliography import (
    BibliographyParser,
    BibliographyEntry,
    RISParser,
    BibTeXParser,
    CSVParser,
    parse_bibliography,
)
from .fuzzy_matcher import (
    FuzzyMatcher,
    MatchResult,
    match_bibliography_to_pdfs,
)
from .resolver import (
    MetadataResolver,
    ResolvedMetadata,
    MetadataSource,
    resolve_pdf_metadata,
)

__all__ = [
    # DOI Extraction
    "DOIExtractor",
    "extract_doi",
    # CrossRef
    "CrossRefClient",
    "CrossRefWork",
    "lookup_doi",
    # OpenAlex
    "OpenAlexClient",
    "OpenAlexWork",
    "search_openalex",
    # LLM Extraction
    "LLMMetadataExtractor",
    "ExtractedBibliographic",
    "ExtractedDomainFields",
    "extract_title_from_pdf_text",
    "extract_domain_fields",
    # Bibliography Parsing
    "BibliographyParser",
    "BibliographyEntry",
    "RISParser",
    "BibTeXParser",
    "CSVParser",
    "parse_bibliography",
    # Fuzzy Matching
    "FuzzyMatcher",
    "MatchResult",
    "match_bibliography_to_pdfs",
    # Resolution
    "MetadataResolver",
    "ResolvedMetadata",
    "MetadataSource",
    "resolve_pdf_metadata",
]
