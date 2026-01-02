"""
DevChat v2.0 SOTA - DOI Extractor

Extract DOI from PDF documents using multiple methods:
1. PDF metadata (XMP, Dublin Core)
2. Regex patterns on first pages
3. URL patterns in references
"""

import re
from pathlib import Path
from typing import Optional, List, TYPE_CHECKING

# Lazy import fitz - it's heavy and not available in production API
# Only used in Modal workers for PDF processing
if TYPE_CHECKING:
    import fitz

from src.utils.logging import get_logger

logger = get_logger(__name__)


def _get_fitz():
    """Lazy import PyMuPDF."""
    try:
        import fitz
        return fitz
    except ImportError:
        raise ImportError(
            "PyMuPDF (fitz) is required for PDF DOI extraction. "
            "Install with: pip install pymupdf"
        )


class DOIExtractor:
    """Extract DOI identifiers from PDF documents."""
    
    # DOI regex patterns (from most specific to most general)
    DOI_PATTERNS = [
        # Standard DOI format
        r'10\.\d{4,9}/[-._;()/:A-Z0-9]+',
        # DOI with doi: prefix
        r'doi:\s*(10\.\d{4,9}/[-._;()/:A-Z0-9]+)',
        # DOI URL format
        r'(?:https?://)?(?:dx\.)?doi\.org/(10\.\d{4,9}/[-._;()/:A-Z0-9]+)',
        # Handle DOIs in parentheses or brackets
        r'DOI[:\s]+(10\.\d{4,9}/[-._;()/:A-Z0-9]+)',
    ]
    
    def __init__(self):
        self._compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.DOI_PATTERNS
        ]
    
    def extract_from_pdf(self, pdf_path: Path) -> Optional[str]:
        """
        Extract DOI from a PDF file.
        
        Tries multiple methods:
        1. PDF metadata
        2. First 3 pages text
        3. Reference section (last pages)
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            DOI string if found, None otherwise
        """
        fitz = _get_fitz()
        try:
            doc = fitz.open(pdf_path)
            
            # Method 1: Check PDF metadata
            doi = self._extract_from_metadata(doc)
            if doi:
                logger.info(f"DOI from metadata: {doi}")
                return doi
            
            # Method 2: Scan first 3 pages (where DOI usually appears)
            doi = self._extract_from_pages(doc, pages=range(min(3, len(doc))))
            if doi:
                logger.info(f"DOI from first pages: {doi}")
                return doi
            
            # Method 3: Check last page (references sometimes have DOI)
            if len(doc) > 3:
                doi = self._extract_from_pages(doc, pages=[len(doc) - 1])
                if doi:
                    logger.info(f"DOI from last page: {doi}")
                    return doi
            
            logger.warning(f"No DOI found in {pdf_path.name}")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting DOI from {pdf_path}: {e}")
            return None
        finally:
            if 'doc' in locals():
                doc.close()
    
    def extract_from_text(self, text: str) -> Optional[str]:
        """
        Extract DOI from raw text.
        
        Args:
            text: Text content to search
            
        Returns:
            DOI string if found, None otherwise
        """
        dois = self._find_all_dois(text)
        return dois[0] if dois else None
    
    def extract_all_from_text(self, text: str) -> List[str]:
        """
        Extract all DOIs from text (useful for reference sections).
        
        Args:
            text: Text content to search
            
        Returns:
            List of unique DOI strings
        """
        return self._find_all_dois(text)
    
    def _extract_from_metadata(self, doc: fitz.Document) -> Optional[str]:
        """Extract DOI from PDF metadata fields."""
        metadata = doc.metadata
        
        # Check common metadata fields
        for field in ['doi', 'subject', 'keywords', 'producer']:
            value = metadata.get(field, '')
            if value:
                doi = self.extract_from_text(value)
                if doi:
                    return doi
        
        # Check XMP metadata if available
        try:
            xmp = doc.xref_get_key(-1, "Metadata")
            if xmp[0] == "stream":
                xmp_text = doc.xref_stream(-1)
                if xmp_text:
                    doi = self.extract_from_text(xmp_text.decode('utf-8', errors='ignore'))
                    if doi:
                        return doi
        except Exception:
            pass
        
        return None
    
    def _extract_from_pages(self, doc: fitz.Document, pages: range) -> Optional[str]:
        """Extract DOI from specified pages."""
        for page_num in pages:
            try:
                page = doc[page_num]
                text = page.get_text()
                doi = self.extract_from_text(text)
                if doi:
                    return doi
            except Exception as e:
                logger.warning(f"Error reading page {page_num}: {e}")
        return None
    
    def _find_all_dois(self, text: str) -> List[str]:
        """Find all unique DOIs in text."""
        dois = set()
        
        for pattern in self._compiled_patterns:
            for match in pattern.finditer(text):
                # Get the DOI (might be in a capture group)
                doi = match.group(1) if match.lastindex else match.group(0)
                # Clean up the DOI
                doi = self._clean_doi(doi)
                if doi and self._validate_doi(doi):
                    dois.add(doi)
        
        return list(dois)
    
    def _clean_doi(self, doi: str) -> str:
        """Clean and normalize a DOI string."""
        # Remove common prefixes
        doi = re.sub(r'^(?:doi:|https?://(?:dx\.)?doi\.org/)', '', doi, flags=re.IGNORECASE)
        
        # Remove trailing punctuation that might have been captured
        doi = doi.rstrip('.,;:)]>')
        
        # Ensure it starts with 10.
        if not doi.startswith('10.'):
            return ''
        
        return doi.strip()
    
    def _validate_doi(self, doi: str) -> bool:
        """Basic DOI format validation."""
        if not doi or not doi.startswith('10.'):
            return False
        
        # Must have registrant code (4+ digits) and suffix
        parts = doi.split('/', 1)
        if len(parts) != 2:
            return False
        
        registrant = parts[0][3:]  # Remove "10."
        if not registrant or not registrant[0].isdigit():
            return False
        
        suffix = parts[1]
        if not suffix or len(suffix) < 1:
            return False
        
        return True


# Convenience function
def extract_doi(pdf_path: Path) -> Optional[str]:
    """Extract DOI from a PDF file."""
    extractor = DOIExtractor()
    return extractor.extract_from_pdf(pdf_path)
