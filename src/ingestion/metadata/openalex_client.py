"""
DevChat v2.0 SOTA - OpenAlex API Client

Query OpenAlex for bibliographic metadata.
OpenAlex is free, open, and has 250M+ works indexed.

API Docs: https://docs.openalex.org/
Rate limit: 100,000 requests/day (polite pool with email)
"""

import httpx
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from src.utils.logging import get_logger

logger = get_logger(__name__)


class OpenAlexWork(BaseModel):
    """Parsed OpenAlex work metadata."""
    
    openalex_id: str  # e.g., "W2741809807"
    doi: Optional[str] = None
    title: str
    authors: List[str]
    author_institutions: Optional[List[str]] = None
    year: Optional[int] = None
    journal: Optional[str] = None
    publisher: Optional[str] = None
    abstract: Optional[str] = None
    url: Optional[str] = None
    open_access_url: Optional[str] = None
    is_open_access: bool = False
    type: Optional[str] = None  # article, book-chapter, etc.
    cited_by_count: Optional[int] = None
    concepts: Optional[List[Dict[str, Any]]] = None  # Topics/keywords with scores
    
    # For development studies
    countries: Optional[List[str]] = None  # Countries mentioned
    sdgs: Optional[List[str]] = None  # Sustainable Development Goals
    
    raw: Optional[Dict[str, Any]] = None


class OpenAlexClient:
    """
    Client for OpenAlex REST API.
    
    Features:
    - DOI lookup
    - Title/author search with fuzzy matching
    - Concept/topic extraction
    - SDG classification (useful for development research)
    """
    
    BASE_URL = "https://api.openalex.org"
    
    def __init__(
        self,
        email: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """
        Initialize OpenAlex client.
        
        Args:
            email: Contact email for polite pool (faster limits)
            timeout: Request timeout in seconds
        """
        self.email = email or "devchat@3ieimpact.org"
        self.timeout = timeout
    
    def _get_params(self, **kwargs) -> Dict[str, Any]:
        """Build request params with polite pool email."""
        params = {"mailto": self.email}
        params.update(kwargs)
        return params
    
    async def get_by_doi(self, doi: str) -> Optional[OpenAlexWork]:
        """
        Get metadata for a DOI.
        
        Args:
            doi: DOI string (with or without URL prefix)
            
        Returns:
            OpenAlexWork with metadata, or None if not found
        """
        # Clean DOI
        doi = doi.strip()
        if not doi.startswith("https://doi.org/"):
            doi = f"https://doi.org/{doi}"
        
        url = f"{self.BASE_URL}/works/{doi}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=self._get_params())
                
                if response.status_code == 404:
                    logger.warning(f"DOI not found in OpenAlex: {doi}")
                    return None
                
                response.raise_for_status()
                data = response.json()
                
                return self._parse_work(data)
                
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAlex API error for {doi}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching from OpenAlex: {e}")
            return None
    
    async def get_by_openalex_id(self, openalex_id: str) -> Optional[OpenAlexWork]:
        """
        Get metadata by OpenAlex ID.
        
        Args:
            openalex_id: OpenAlex ID (e.g., "W2741809807")
            
        Returns:
            OpenAlexWork with metadata, or None if not found
        """
        url = f"{self.BASE_URL}/works/{openalex_id}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=self._get_params())
                
                if response.status_code == 404:
                    return None
                
                response.raise_for_status()
                return self._parse_work(response.json())
                
        except Exception as e:
            logger.error(f"Error fetching OpenAlex ID {openalex_id}: {e}")
            return None
    
    async def search(
        self,
        title: Optional[str] = None,
        author: Optional[str] = None,
        query: Optional[str] = None,
        per_page: int = 10,
    ) -> List[OpenAlexWork]:
        """
        Search OpenAlex works.
        
        Args:
            title: Search by title
            author: Filter by author name
            query: Free-text search across all fields
            per_page: Number of results
            
        Returns:
            List of matching works
        """
        url = f"{self.BASE_URL}/works"
        
        # Build filter
        filters = []
        if title:
            # Use search instead of filter for fuzzy matching
            pass
        
        params = self._get_params(per_page=per_page)
        
        # OpenAlex uses 'search' for fuzzy title matching
        if title:
            params["search"] = title
        
        if author:
            filters.append(f"author.search:{author}")
        
        if filters:
            params["filter"] = ",".join(filters)
        
        if query:
            params["search"] = query
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                works = []
                for item in data.get("results", []):
                    work = self._parse_work(item)
                    if work:
                        works.append(work)
                
                return works
                
        except Exception as e:
            logger.error(f"Error searching OpenAlex: {e}")
            return []
    
    async def search_by_title_author(
        self,
        title: str,
        author: Optional[str] = None,
        year: Optional[int] = None,
    ) -> Optional[OpenAlexWork]:
        """
        Search for a specific work by title and author.
        Returns the best match if found.
        
        Args:
            title: Work title
            author: First author name (optional but recommended)
            year: Publication year (optional, helps disambiguation)
            
        Returns:
            Best matching work, or None
        """
        results = await self.search(title=title, author=author, per_page=5)
        
        if not results:
            return None
        
        # If we have year, prefer matching year
        if year:
            for work in results:
                if work.year == year:
                    return work
        
        # Return first (best) match
        return results[0]
    
    def _parse_work(self, data: Dict[str, Any]) -> Optional[OpenAlexWork]:
        """Parse OpenAlex API response into OpenAlexWork."""
        try:
            openalex_id = data.get("id", "").split("/")[-1]  # Extract ID from URL
            if not openalex_id:
                return None
            
            # Extract title
            title = data.get("title") or data.get("display_name") or "Unknown Title"
            
            # Extract authors
            authors = []
            author_institutions = []
            for authorship in data.get("authorships", []):
                author_data = authorship.get("author", {})
                name = author_data.get("display_name", "")
                if name:
                    authors.append(name)
                
                # Get institution
                institutions = authorship.get("institutions", [])
                if institutions:
                    inst_name = institutions[0].get("display_name", "")
                    if inst_name:
                        author_institutions.append(inst_name)
            
            # Extract DOI
            doi = data.get("doi")
            if doi and doi.startswith("https://doi.org/"):
                doi = doi[16:]
            
            # Extract source (journal)
            source = data.get("primary_location", {}).get("source", {})
            journal = source.get("display_name") if source else None
            publisher = source.get("publisher") if source else None
            
            # Extract abstract (inverted index format)
            abstract = None
            abstract_inverted = data.get("abstract_inverted_index")
            if abstract_inverted:
                abstract = self._reconstruct_abstract(abstract_inverted)
            
            # Open access info
            oa_info = data.get("open_access", {})
            is_oa = oa_info.get("is_oa", False)
            oa_url = oa_info.get("oa_url")
            
            # Concepts (topics)
            concepts = []
            for concept in data.get("concepts", [])[:10]:  # Top 10
                concepts.append({
                    "name": concept.get("display_name"),
                    "score": concept.get("score"),
                    "level": concept.get("level"),
                })
            
            # SDGs
            sdgs = []
            for sdg in data.get("sustainable_development_goals", []):
                sdgs.append(sdg.get("display_name", ""))
            
            # Countries (from author affiliations)
            countries = set()
            for authorship in data.get("authorships", []):
                for inst in authorship.get("institutions", []):
                    country = inst.get("country_code")
                    if country:
                        countries.add(country)
            
            return OpenAlexWork(
                openalex_id=openalex_id,
                doi=doi,
                title=title,
                authors=authors,
                author_institutions=author_institutions or None,
                year=data.get("publication_year"),
                journal=journal,
                publisher=publisher,
                abstract=abstract,
                url=data.get("doi") or f"https://openalex.org/{openalex_id}",
                open_access_url=oa_url,
                is_open_access=is_oa,
                type=data.get("type"),
                cited_by_count=data.get("cited_by_count"),
                concepts=concepts or None,
                countries=list(countries) if countries else None,
                sdgs=sdgs or None,
                raw=data,
            )
            
        except Exception as e:
            logger.error(f"Error parsing OpenAlex response: {e}")
            return None
    
    def _reconstruct_abstract(self, inverted_index: Dict[str, List[int]]) -> str:
        """
        Reconstruct abstract from OpenAlex inverted index format.
        
        OpenAlex stores abstracts as {word: [positions]} for compression.
        """
        if not inverted_index:
            return ""
        
        # Build position -> word mapping
        words = {}
        for word, positions in inverted_index.items():
            for pos in positions:
                words[pos] = word
        
        # Reconstruct in order
        if not words:
            return ""
        
        max_pos = max(words.keys())
        abstract_words = [words.get(i, "") for i in range(max_pos + 1)]
        
        return " ".join(w for w in abstract_words if w)


# Convenience function
async def search_openalex(title: str, author: Optional[str] = None) -> Optional[OpenAlexWork]:
    """Search OpenAlex for a work by title and author."""
    client = OpenAlexClient()
    return await client.search_by_title_author(title, author)
