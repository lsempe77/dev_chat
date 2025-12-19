"""
DevChat v2.0 SOTA - LLM Metadata Extractor

Use LLM to extract metadata when:
1. No DOI found - extract title/authors from first page
2. Fill domain-specific gaps (country, sector, study_type)

Uses structured output for reliable extraction.
"""

import os
import json
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from src.utils.logging import get_logger

logger = get_logger(__name__)


def get_openrouter_api_key() -> Optional[str]:
    """Get OpenRouter API key from env or settings."""
    # First try environment variable (for Modal)
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    
    # Fall back to settings module
    try:
        from src.config.settings import settings
        return settings.openrouter_api_key
    except Exception:
        return None


class ExtractedBibliographic(BaseModel):
    """LLM-extracted bibliographic info from PDF text."""
    title: str
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    journal: Optional[str] = None
    doi: Optional[str] = None
    abstract: Optional[str] = None


class ExtractedDomainFields(BaseModel):
    """LLM-extracted domain-specific fields for development research."""
    countries: List[str] = Field(default_factory=list, description="Countries studied/mentioned")
    regions: List[str] = Field(default_factory=list, description="Regions (e.g., Sub-Saharan Africa, South Asia)")
    sectors: List[str] = Field(default_factory=list, description="Sectors (e.g., education, health, agriculture)")
    study_type: Optional[str] = Field(None, description="RCT, quasi-experimental, systematic-review, observational, etc.")
    intervention_type: Optional[str] = Field(None, description="Type of intervention studied")
    target_population: Optional[str] = Field(None, description="Target population of the study")


class LLMMetadataExtractor:
    """
    Extract metadata from text using LLM.
    
    Two main use cases:
    1. Extract bibliographic info when DOI is not available
    2. Fill domain-specific gaps (countries, sectors, study type)
    """
    
    BIBLIOGRAPHIC_PROMPT = """Extract bibliographic metadata from this academic paper's first page.

TEXT:
{text}

Extract the following fields as JSON:
- title: The paper's title
- authors: List of author names (format: "First Last")
- year: Publication year (integer)
- journal: Journal or publication name
- doi: DOI if visible (format: 10.xxxx/yyyy)
- abstract: Abstract text if present (first 500 chars)

Return ONLY valid JSON, no explanation."""

    DOMAIN_FIELDS_PROMPT = """Analyze this academic paper about development/impact evaluation and extract domain-specific metadata.

TITLE: {title}

ABSTRACT:
{abstract}

TEXT EXCERPT:
{text}

Extract the following as JSON:
- countries: List of countries studied or mentioned (use official names)
- regions: List of regions (e.g., "Sub-Saharan Africa", "South Asia", "Latin America")
- sectors: List of sectors (e.g., "education", "health", "agriculture", "finance", "infrastructure")
- study_type: One of ["RCT", "quasi-experimental", "systematic-review", "meta-analysis", "observational", "qualitative", "mixed-methods", "other"]
- intervention_type: Type of intervention (e.g., "cash transfer", "training program", "infrastructure investment")
- target_population: Target population (e.g., "farmers", "students", "women", "households")

Return ONLY valid JSON, no explanation."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize extractor.
        
        Args:
            api_key: OpenRouter API key. If not provided, will look in env/settings.
        """
        self._client = None
        self._api_key = api_key or get_openrouter_api_key()
    
    @property
    def client(self):
        """Lazy-load LLM client."""
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client
    
    async def extract_bibliographic(self, text: str) -> Optional[ExtractedBibliographic]:
        """
        Extract bibliographic info from PDF first page text.
        
        Args:
            text: Text from first 1-2 pages of PDF
            
        Returns:
            ExtractedBibliographic or None on failure
        """
        prompt = self.BIBLIOGRAPHIC_PROMPT.format(text=text[:4000])
        
        try:
            response = await self._call_llm(prompt)
            if not response:
                return None
            
            # Parse JSON response
            data = self._parse_json_response(response)
            if not data:
                return None
            
            return ExtractedBibliographic(
                title=data.get("title", "Unknown Title"),
                authors=data.get("authors", []),
                year=data.get("year"),
                journal=data.get("journal"),
                doi=data.get("doi"),
                abstract=data.get("abstract"),
            )
            
        except Exception as e:
            logger.error(f"Error extracting bibliographic info: {e}")
            return None
    
    async def extract_domain_fields(
        self,
        title: str,
        abstract: Optional[str] = None,
        text: Optional[str] = None,
    ) -> Optional[ExtractedDomainFields]:
        """
        Extract domain-specific fields for development research.
        
        Args:
            title: Paper title
            abstract: Abstract text
            text: Additional text excerpt
            
        Returns:
            ExtractedDomainFields or None on failure
        """
        prompt = self.DOMAIN_FIELDS_PROMPT.format(
            title=title,
            abstract=abstract or "Not available",
            text=(text or "")[:2000],
        )
        
        try:
            response = await self._call_llm(prompt)
            if not response:
                return None
            
            data = self._parse_json_response(response)
            if not data:
                return None
            
            return ExtractedDomainFields(
                countries=data.get("countries", []),
                regions=data.get("regions", []),
                sectors=data.get("sectors", []),
                study_type=data.get("study_type"),
                intervention_type=data.get("intervention_type"),
                target_population=data.get("target_population"),
            )
            
        except Exception as e:
            logger.error(f"Error extracting domain fields: {e}")
            return None
    
    async def _call_llm(self, prompt: str) -> Optional[str]:
        """Call LLM via OpenRouter."""
        if not self._api_key:
            logger.warning("No OpenRouter API key available, skipping LLM extraction")
            return None
        
        try:
            response = await self.client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "openai/gpt-4o-mini",  # Fast and cheap for extraction
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a metadata extraction assistant. Extract structured data from academic papers. Always respond with valid JSON only."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,  # Low temperature for consistency
                    "max_tokens": 1000,
                },
            )
            
            response.raise_for_status()
            data = response.json()
            
            return data["choices"][0]["message"]["content"]
            
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None
    
    def _parse_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from LLM response, handling common issues."""
        if not response:
            return None
        
        # Clean up response
        text = response.strip()
        
        # Remove markdown code blocks if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        
        # Try to find JSON object
        try:
            # Direct parse
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Try to extract JSON from text
        import re
        json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        logger.warning(f"Could not parse JSON from response: {text[:200]}...")
        return None
    
    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Convenience functions
async def extract_title_from_pdf_text(text: str) -> Optional[ExtractedBibliographic]:
    """Extract bibliographic info from PDF text."""
    extractor = LLMMetadataExtractor()
    try:
        return await extractor.extract_bibliographic(text)
    finally:
        await extractor.close()


async def extract_domain_fields(
    title: str,
    abstract: Optional[str] = None,
    text: Optional[str] = None,
) -> Optional[ExtractedDomainFields]:
    """Extract domain-specific fields."""
    extractor = LLMMetadataExtractor()
    try:
        return await extractor.extract_domain_fields(title, abstract, text)
    finally:
        await extractor.close()
