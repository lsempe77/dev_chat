"""
Metadata Resolution Module

Handles metadata enrichment via CrossRef, OpenAlex, and LLM extraction.
"""

import asyncio
import json
import os
import re
from typing import Optional, Dict, Any

import httpx


# ============================================================================
# Metadata Resolution
# ============================================================================

def resolve_metadata(
    content: str,
    title: Optional[str] = None,
    authors: Optional[list] = None,
    year: Optional[int] = None,
    pdf_filename: Optional[str] = None,
) -> dict:
    """
    Resolve rich metadata using CrossRef, OpenAlex, and LLM.
    
    Flow:
    1. Extract DOI from content
    2. If DOI found: CrossRef lookup → OpenAlex enrichment
    3. If no DOI: Search by title/author
    4. LLM fills domain-specific gaps (countries, sectors, study_type)
    """
    import asyncio
    import httpx
    
    # Default metadata
    metadata = {
        "title": title or "Unknown Title",
        "authors": authors or [],
        "year": year,
        "doi": None,
        "item_type": None,
        "journal": None,
        "volume": None,
        "issue": None,
        "pages": None,
        "publisher": None,
        "abstract": None,
        "cited_by_count": None,
        "is_open_access": False,
        "countries": [],
        "sectors": [],
        "study_type": None,
        "intervention_type": None,
        "sdgs": [],
        "keywords": [],
        "metadata_source": "extraction",
        "metadata_confidence": 0.3,
        "needs_review": True,
        "pdf_name": pdf_filename,
    }
    
    # Step 1: Extract DOI from content
    doi = extract_doi_from_text(content[:10000])
    if doi:
        metadata["doi"] = doi
        print(f"  Found DOI: {doi}")
    
    # Step 2: CrossRef + OpenAlex lookup
    async def lookup_apis():
        async with httpx.AsyncClient(timeout=30.0) as client:
            crossref_data = None
            openalex_data = None
            
            if doi:
                # CrossRef lookup
                try:
                    crossref_url = f"https://api.crossref.org/works/{doi}"
                    resp = await client.get(
                        crossref_url,
                        headers={"User-Agent": "DevChat/2.0 (mailto:dev@example.com)"}
                    )
                    if resp.status_code == 200:
                        crossref_data = resp.json().get("message", {})
                        print(f"  CrossRef: found")
                except Exception as e:
                    print(f"  CrossRef error: {e}")
                
                # OpenAlex lookup by DOI
                try:
                    openalex_url = f"https://api.openalex.org/works/https://doi.org/{doi}"
                    resp = await client.get(
                        openalex_url,
                        headers={"User-Agent": "mailto:dev@example.com"}
                    )
                    if resp.status_code == 200:
                        openalex_data = resp.json()
                        print(f"  OpenAlex: found")
                except Exception as e:
                    print(f"  OpenAlex error: {e}")
            
            elif title and len(title) > 10:
                # Search by title
                try:
                    search_title = title[:200].replace('"', '')
                    openalex_url = f"https://api.openalex.org/works?search={search_title}&per_page=1"
                    resp = await client.get(
                        openalex_url,
                        headers={"User-Agent": "mailto:dev@example.com"}
                    )
                    if resp.status_code == 200:
                        results = resp.json().get("results", [])
                        if results:
                            openalex_data = results[0]
                            print(f"  OpenAlex: found via title search")
                except Exception as e:
                    print(f"  OpenAlex search error: {e}")
            
            return crossref_data, openalex_data
    
    try:
        crossref_data, openalex_data = asyncio.run(lookup_apis())
        
        # Merge CrossRef data
        if crossref_data:
            metadata = _merge_crossref_data(metadata, crossref_data)
        
        # Merge OpenAlex data
        if openalex_data:
            metadata = _merge_openalex_data(metadata, openalex_data, is_primary=not crossref_data)
    
    except Exception as e:
        print(f"  Metadata lookup error: {e}")
    
    # Step 3: LLM gap-filling for domain fields
    if not metadata["sectors"] or not metadata["study_type"]:
        openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        if openrouter_key:
            try:
                llm_result = asyncio.run(
                    llm_extract_domain_fields(
                        title=metadata["title"],
                        abstract=metadata.get("abstract") or content[:3000],
                        api_key=openrouter_key,
                    )
                )
                if llm_result:
                    if not metadata["countries"] and llm_result.get("countries"):
                        metadata["countries"] = llm_result["countries"]
                    if llm_result.get("sectors"):
                        metadata["sectors"] = llm_result["sectors"]
                    if llm_result.get("study_type"):
                        metadata["study_type"] = llm_result["study_type"]
                    if llm_result.get("intervention_type"):
                        metadata["intervention_type"] = llm_result["intervention_type"]
                    print(f"  LLM enrichment: sectors={metadata['sectors']}, study_type={metadata['study_type']}")
            except Exception as e:
                print(f"  LLM enrichment error: {e}")
    
    return metadata


def _merge_crossref_data(metadata: dict, crossref_data: dict) -> dict:
    """Merge CrossRef API response into metadata."""
    metadata["title"] = crossref_data.get("title", [metadata["title"]])[0] if crossref_data.get("title") else metadata["title"]
    
    # Extract authors
    cr_authors = crossref_data.get("author", [])
    if cr_authors:
        metadata["authors"] = [
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in cr_authors
        ]
    
    # Extract year from published date
    published = crossref_data.get("published-print") or crossref_data.get("published-online") or {}
    date_parts = published.get("date-parts", [[]])[0]
    if date_parts:
        metadata["year"] = date_parts[0]
    
    metadata["journal"] = crossref_data.get("container-title", [None])[0] if crossref_data.get("container-title") else None
    metadata["publisher"] = crossref_data.get("publisher")
    metadata["cited_by_count"] = crossref_data.get("is-referenced-by-count")
    metadata["doi"] = crossref_data.get("DOI") or metadata["doi"]
    metadata["volume"] = crossref_data.get("volume")
    metadata["issue"] = crossref_data.get("issue")
    metadata["pages"] = crossref_data.get("page")
    
    # Map CrossRef type to our item_type
    crossref_type = crossref_data.get("type", "")
    item_type_map = {
        "journal-article": "journalArticle",
        "book-chapter": "bookSection",
        "book": "book",
        "proceedings-article": "conferencePaper",
        "report": "report",
        "report-series": "report",
        "dissertation": "thesis",
        "posted-content": "preprint",
        "dataset": "dataset",
        "monograph": "book",
        "reference-book": "book",
        "edited-book": "book",
    }
    metadata["item_type"] = item_type_map.get(crossref_type, "document")
    
    metadata["metadata_source"] = "crossref"
    metadata["metadata_confidence"] = 0.8
    metadata["needs_review"] = False
    
    return metadata


def _merge_openalex_data(metadata: dict, openalex_data: dict, is_primary: bool = False) -> dict:
    """Merge OpenAlex API response into metadata."""
    if is_primary:
        metadata["title"] = openalex_data.get("title") or metadata["title"]
        
        authorships = openalex_data.get("authorships", [])
        if authorships and not metadata["authors"]:
            metadata["authors"] = [
                a.get("author", {}).get("display_name", "")
                for a in authorships
            ]
        
        metadata["year"] = openalex_data.get("publication_year") or metadata["year"]
        
        primary_loc = openalex_data.get("primary_location", {}) or {}
        source = primary_loc.get("source", {}) or {}
        metadata["journal"] = source.get("display_name") or metadata["journal"]
        
        metadata["doi"] = openalex_data.get("doi", "").replace("https://doi.org/", "") if openalex_data.get("doi") else metadata["doi"]
        metadata["cited_by_count"] = openalex_data.get("cited_by_count") or metadata["cited_by_count"]
        
        biblio = openalex_data.get("biblio", {}) or {}
        metadata["volume"] = biblio.get("volume") or metadata.get("volume")
        metadata["issue"] = biblio.get("issue") or metadata.get("issue")
        first_page = biblio.get("first_page")
        last_page = biblio.get("last_page")
        if first_page and last_page:
            metadata["pages"] = f"{first_page}-{last_page}"
        elif first_page:
            metadata["pages"] = first_page
        
        openalex_type = openalex_data.get("type", "")
        oa_type_map = {
            "article": "journalArticle",
            "book": "book",
            "book-chapter": "bookSection",
            "dissertation": "thesis",
            "dataset": "dataset",
            "preprint": "preprint",
            "report": "report",
            "review": "journalArticle",
            "paratext": "document",
        }
        metadata["item_type"] = oa_type_map.get(openalex_type, "journalArticle")
        
        metadata["metadata_source"] = "openalex"
        metadata["metadata_confidence"] = 0.7
        metadata["needs_review"] = False
    
    # Always use OpenAlex for enrichment
    oa = openalex_data.get("open_access", {}) or {}
    metadata["is_open_access"] = oa.get("is_oa", False)
    
    sdgs = openalex_data.get("sustainable_development_goals", [])
    metadata["sdgs"] = [s.get("display_name") for s in sdgs if s.get("display_name")]
    
    concepts = openalex_data.get("concepts", [])
    metadata["keywords"] = [
        c.get("display_name") for c in concepts[:10]
        if c.get("display_name") and c.get("score", 0) > 0.3
    ]
    
    authorships = openalex_data.get("authorships", [])
    countries = set()
    for a in authorships:
        for inst in a.get("institutions", []):
            if inst.get("country_code"):
                countries.add(inst["country_code"])
    metadata["countries"] = list(countries)
    
    return metadata


# ============================================================================
# DOI Extraction
# ============================================================================

def extract_doi_from_text(text: str) -> Optional[str]:
    """Extract DOI from text using regex patterns."""
    if not text:
        return None
    
    patterns = [
        r'10\.\d{4,}/[^\s\]>)\'"]+',
        r'(?:doi\.org/|doi:)\s*(10\.\d{4,}/[^\s\]>)\'"]+)',
        r'DOI[:\s]+\[?(10\.\d{4,}/[^\s\]>)\'"]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            doi = match.group(1) if match.lastindex else match.group(0)
            doi = re.sub(r'[.,;:\'")\]]+$', '', doi)
            return doi
    
    return None


# ============================================================================
# LLM Extraction
# ============================================================================

async def llm_extract_domain_fields(
    title: str,
    abstract: str,
    api_key: str,
) -> Optional[dict]:
    """Use LLM to extract domain-specific fields."""
    import httpx
    import json
    
    prompt = f"""Analyze this academic paper about development/impact evaluation and extract domain-specific metadata.

TITLE: {title}

ABSTRACT:
{abstract[:2000]}

Extract the following as JSON:
- countries: List of countries studied or mentioned (use official names)
- sectors: List of sectors (e.g., "education", "health", "agriculture", "finance")
- study_type: One of ["RCT", "quasi-experimental", "systematic-review", "meta-analysis", "observational", "qualitative", "mixed-methods", "other"]
- intervention_type: Type of intervention studied

Return ONLY valid JSON, no explanation."""

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a metadata extraction assistant. Always respond with valid JSON only."
                    },
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 500,
            },
        )
        
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
        
        return json.loads(content)


async def classify_study_design_llm(
    title: str,
    abstract_or_content: str,
    api_key: str,
) -> dict:
    """
    Classify study design using LLM with OpenRouter.
    
    Returns dict with study_design, study_design_confidence, study_design_reasoning.
    """
    import httpx
    import json
    
    prompt = f"""Analyze this research document and classify its primary study design.

DOCUMENT TITLE: {title or "Unknown"}

ABSTRACT/CONTENT:
{abstract_or_content[:4000] if abstract_or_content else "No abstract available"}

STUDY DESIGN CATEGORIES:

EXPERIMENTAL (randomized assignment):
- rct: Randomized Controlled Trial - random assignment to treatment/control
- cluster_rct: Cluster RCT - randomization at group/community level

QUASI-EXPERIMENTAL (exploits natural variation):
- regression_discontinuity: Uses a cutoff/threshold for assignment
- difference_in_differences: Compares before/after with treatment/control groups
- instrumental_variable: Uses exogenous variation to identify causal effects
- propensity_score_matching: Statistically matches treatment/control groups
- interrupted_time_series: Analyzes trend changes after intervention
- synthetic_control: Constructs synthetic counterfactual from donor pool

OBSERVATIONAL (no experimental manipulation):
- cohort: Follows groups over time
- cross_sectional: Point-in-time measurement
- case_control: Compares cases with controls retrospectively
- panel: Repeated observations of same units over time

QUALITATIVE (non-numerical analysis):
- qualitative: Interviews, focus groups, thematic analysis
- mixed_methods: Combines quantitative and qualitative approaches
- case_study: In-depth analysis of specific case(s)
- ethnography: Immersive observation of communities/cultures

SYNTHESIS:
- systematic_review: Systematic literature review
- meta_analysis: Statistical synthesis of multiple studies

OTHER:
- modeling: Simulations, economic modeling, theoretical models
- descriptive: Describes patterns without causal claims
- theory: Theoretical/conceptual paper

Return JSON:
{{
    "study_design": "one of the codes above (e.g., 'rct', 'difference_in_differences')",
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation"
}}

If you cannot determine, return {{"study_design": "unknown", "confidence": 0.0, "reasoning": "Could not determine"}}
"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "openai/gpt-4o-mini",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a research methodology expert. Classify study designs accurately. Return only valid JSON."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.0,
                    "max_tokens": 400,
                },
            )
            
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            content = content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            
            result = json.loads(content)
            return {
                "study_design": result.get("study_design", "unknown"),
                "study_design_confidence": float(result.get("confidence", 0.5)),
                "study_design_reasoning": result.get("reasoning", ""),
            }
            
    except Exception as e:
        print(f"  ⚠ Study design classification failed: {e}")
        return {
            "study_design": "unknown",
            "study_design_confidence": 0.0,
            "study_design_reasoning": f"Classification error: {str(e)}",
        }
