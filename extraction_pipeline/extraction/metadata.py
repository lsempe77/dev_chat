"""
Metadata Extraction
===================

Extract paper metadata from MineRU JSON documents.
"""

import json as json_module
from typing import Dict, Any

from ..core.llm_client import call_llm


def extract_metadata(doc: dict, study_id: str) -> dict:
    """
    Extract paper metadata directly from MineRU JSON.
    
    Args:
        doc: MineRU JSON document
        study_id: Study identifier
        
    Returns:
        Metadata dictionary with basic fields
    """
    return {
        'study_id': study_id,
        'title': doc.get('title', ''),
        'authors': doc.get('authors', []),
        'year': doc.get('year', ''),
        'abstract': doc.get('abstract', ''),
        'page_count': doc.get('page_count', 0),
        'source_key': doc.get('source_key', '')
    }


def extract_metadata_llm(doc: dict, study_id: str) -> dict:
    """
    Extract comprehensive paper metadata using LLM.
    Fills gaps not captured by MineRU parsing.
    
    Args:
        doc: MineRU JSON document
        study_id: Study identifier
        
    Returns:
        Enriched metadata dictionary with LLM-extracted fields
    """
    # Get first ~4000 chars (title page + abstract + intro)
    content = doc.get('content', '')[:4000]
    abstract = doc.get('abstract', '')
    
    prompt = f"""Extract metadata from this academic paper. Return ONLY a JSON object with these fields.
If a field cannot be determined, use null.

PAPER TEXT:
{content}

ABSTRACT:
{abstract}

Return JSON with:
{{
  "authors": "Author1, Author2, Author3",
  "year": 2021,
  "country": "Niger",
  "countries_list": ["Niger"],
  "study_design": "RCT",
  "is_experimental": true,
  "intervention_name": "Multi-faceted graduation program",
  "follow_up_months": 18,
  "sample_description": "Female beneficiaries of cash transfer program"
}}

JSON only, no explanation:"""

    result = call_llm(prompt, max_tokens=300)
    
    # Parse JSON response
    try:
        # Clean up response (remove markdown code blocks if present)
        result = result.strip()
        if result.startswith('```'):
            result = result.split('```')[1]
            if result.startswith('json'):
                result = result[4:]
        result = result.strip()
        
        parsed = json_module.loads(result)
    except:
        parsed = {}
    
    # Merge with MineRU metadata (MineRU takes precedence for title, year if present)
    return {
        'study_id': study_id,
        'title': doc.get('title', ''),
        'authors': parsed.get('authors', '') or ', '.join(doc.get('authors', [])),
        'year': doc.get('year') or parsed.get('year'),
        'abstract': doc.get('abstract', ''),
        'page_count': doc.get('page_count', 0),
        'source_key': doc.get('source_key', ''),
        # NEW FIELDS from LLM
        'country': parsed.get('country'),
        'countries_list': parsed.get('countries_list', []),
        'study_design': parsed.get('study_design'),
        'is_experimental': parsed.get('is_experimental'),
        'intervention_name': parsed.get('intervention_name'),
        'follow_up_months': parsed.get('follow_up_months'),
        'sample_description': parsed.get('sample_description'),
    }


__all__ = [
    'extract_metadata',
    'extract_metadata_llm',
]
