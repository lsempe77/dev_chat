"""
DevChat v2.0 SOTA - CrossRef API Client

Query CrossRef for bibliographic metadata by DOI.
CrossRef is the authoritative source for publisher-provided metadata.

API Docs: https://api.crossref.org/swagger-ui/index.html
Polite pool: Include email in User-Agent for faster rate limits (50/sec vs 1/sec)
"""

import httpx
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime

from src.utils.logging import get_logger

logger = get_logger(__name__)


class CrossRefWork(BaseModel):
    """Parsed CrossRef work metadata."""
    
    doi: str
    title: str
    authors: List[str]
    year: Optional[int] = None
    journal: Optional[str] = None
    publisher: Optional[str] = None
    abstract: Optional[str] = None
    url: Optional[str] = None
    issn: Optional[List[str]] = None
    subject: Optional[List[str]] = None
    type: Optional[str] = None  # journal-article, book-chapter, etc.
    cited_by_count: Optional[int] = None
    is_open_access: Optional[bool] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    
    # Raw response for debugging
    raw: Optional[Dict[str, Any]] = None


class CrossRefClient:
    """
    Client for CrossRef REST API.
    
    Features:
    - DOI lookup with full metadata
    - Title/author search (fuzzy)
    - Polite pool support (faster rate limits with email)
    """
    
    BASE_URL = "https://api.crossref.org"
    
    def __init__(
        self,
        email: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """
        Initialize CrossRef client.
        
        Args:
            email: Contact email for polite pool (recommended)
            timeout: Request timeout in seconds
        """
        self.email = email or "devchat@3ieimpact.org"
        self.timeout = timeout
        
        # Set up headers for polite pool
        self.headers = {
            "User-Agent": f"DevChat/2.0 (https://3ieimpact.org; mailto:{self.email})",
            "Accept": "application/json",
        }
    
    async def get_by_doi(self, doi: str) -> Optional[CrossRefWork]:
        """
        Get metadata for a DOI.
        
        Args:
            doi: DOI string (without URL prefix)
            
        Returns:
            CrossRefWork with metadata, or None if not found
        """
        # Clean DOI
        doi = doi.strip()
        if doi.startswith("https://doi.org/"):
            doi = doi[16:]
        elif doi.startswith("http://doi.org/"):
            doi = doi[15:]
        
        url = f"{self.BASE_URL}/works/{doi}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self.headers)
                
                if response.status_code == 404:
                    logger.warning(f"DOI not found in CrossRef: {doi}")
                    return None
                
                response.raise_for_status()
                data = response.json()
                
                return self._parse_work(data.get("message", {}))
                
        except httpx.HTTPStatusError as e:
            logger.error(f"CrossRef API error for {doi}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching from CrossRef: {e}")
            return None
    
    async def search_by_title(
        self,
        title: str,
        author: Optional[str] = None,
        rows: int = 5,
    ) -> List[CrossRefWork]:
        """
        Search CrossRef by title (and optionally author).
        
        Args:
            title: Title to search for
            author: Optional author name to filter
            rows: Number of results to return
            
        Returns:
            List of matching works
        """
        params = {
            "query.title": title,
            "rows": rows,
            "select": "DOI,title,author,published,container-title,publisher,abstract,type,is-referenced-by-count",
        }
        
        if author:
            params["query.author"] = author
        
        url = f"{self.BASE_URL}/works"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                
                works = []
                for item in data.get("message", {}).get("items", []):
                    work = self._parse_work(item)
                    if work:
                        works.append(work)
                
                return works
                
        except Exception as e:
            logger.error(f"Error searching CrossRef: {e}")
            return []
    
    def _parse_work(self, data: Dict[str, Any]) -> Optional[CrossRefWork]:
        """Parse CrossRef API response into CrossRefWork."""
        try:
            # Extract DOI
            doi = data.get("DOI", "")
            if not doi:
                return None
            
            # Extract title (it's a list)
            titles = data.get("title", [])
            title = titles[0] if titles else "Unknown Title"
            
            # Extract authors
            authors = []
            for author in data.get("author", []):
                given = author.get("given", "")
                family = author.get("family", "")
                if given and family:
                    authors.append(f"{given} {family}")
                elif family:
                    authors.append(family)
            
            # Extract year from published date
            year = None
            published = data.get("published") or data.get("published-print") or data.get("published-online")
            if published:
                date_parts = published.get("date-parts", [[]])
                if date_parts and date_parts[0]:
                    year = date_parts[0][0]
            
            # Extract journal/container
            container = data.get("container-title", [])
            journal = container[0] if container else None
            
            # Extract abstract (may contain HTML/JATS)
            abstract = data.get("abstract")
            if abstract:
                # Basic cleanup of JATS XML tags
                import re
                abstract = re.sub(r'<[^>]+>', '', abstract)
                abstract = abstract.strip()
            
            return CrossRefWork(
                doi=doi,
                title=title,
                authors=authors,
                year=year,
                journal=journal,
                publisher=data.get("publisher"),
                abstract=abstract,
                url=f"https://doi.org/{doi}",
                issn=data.get("ISSN"),
                subject=data.get("subject"),
                type=data.get("type"),
                cited_by_count=data.get("is-referenced-by-count"),
                is_open_access=data.get("is-oa"),
                volume=data.get("volume"),
                issue=data.get("issue"),
                pages=data.get("page"),
                raw=data,
            )
            
        except Exception as e:
            logger.error(f"Error parsing CrossRef response: {e}")
            return None


# Convenience function
async def lookup_doi(doi: str) -> Optional[CrossRefWork]:
    """Look up metadata for a DOI via CrossRef."""
    client = CrossRefClient()
    return await client.get_by_doi(doi)
