"""
Study Design Classification Service

Classifies research documents by study design (RCT, quasi-experimental, etc.)
using LLM analysis of title and abstract.
"""

import json
import logging
import os
from typing import Optional, Tuple

from src.config.study_designs import (
    StudyDesign,
    get_classification_prompt,
    parse_study_design,
    get_study_design_info,
)
from src.config.settings import settings

logger = logging.getLogger(__name__)


def _get_llm():
    """Get OpenRouter LLM client."""
    from llama_index.llms.openai_like import OpenAILike
    return OpenAILike(
        model="openai/gpt-4o-mini",
        api_key=settings.openrouter_api_key,
        api_base="https://openrouter.ai/api/v1",
        temperature=0.0,
        max_tokens=500,
    )


async def classify_study_design(
    title: str,
    abstract: str,
    model: str = "openai/gpt-4o-mini",
) -> Tuple[StudyDesign, float, str]:
    """
    Classify a document's study design using LLM.
    
    Args:
        title: Document title
        abstract: Document abstract or first ~4000 chars of content
        model: LLM model to use
        
    Returns:
        Tuple of (StudyDesign, confidence, reasoning)
    """
    if not title and not abstract:
        return StudyDesign.UNKNOWN, 0.0, "No title or abstract provided"
    
    prompt = get_classification_prompt(title, abstract)
    
    try:
        llm = _get_llm()
        response = await llm.acomplete(prompt)
        response_text = str(response)
        
        # Parse JSON response
        try:
            # Try to extract JSON from response
            text = response_text.strip()
            if text.startswith("```"):
                # Remove markdown code blocks
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            
            data = json.loads(text)
            
            design_str = data.get("study_design", "unknown")
            confidence = float(data.get("confidence", 0.5))
            reasoning = data.get("reasoning", "")
            
            # Parse the design string into enum
            design = parse_study_design(design_str)
            
            logger.info(f"Classified '{title[:50]}...' as {design.value} (conf: {confidence:.2f})")
            return design, confidence, reasoning
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse classification JSON: {e}")
            # Try to extract study design from plain text
            design = parse_study_design(response_text)
            return design, 0.3, f"Parsed from text: {response_text[:100]}"
            
    except Exception as e:
        logger.error(f"Study design classification failed: {e}")
        return StudyDesign.UNKNOWN, 0.0, f"Classification error: {str(e)}"


async def get_document_text_from_qdrant(doc_id: str, project_id: str, max_chars: int = 8000) -> str:
    """
    Fetch document text from Qdrant chunks when abstract is not available.
    
    Args:
        doc_id: The doc_id to search for in Qdrant
        project_id: The RAG project ID (used for collection name)
        max_chars: Maximum characters to return
        
    Returns:
        Concatenated text from the first few chunks
    """
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    try:
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )
        
        # Collection name format: rag_{project_id}
        collection_name = f"rag_{project_id}"
        
        # Search for chunks with this doc_id
        results = client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="doc_id",
                        match=MatchValue(value=doc_id)
                    )
                ]
            ),
            limit=10,  # Get first 10 chunks
            with_payload=True,
        )
        
        points = results[0] if results else []
        
        if not points:
            return ""
        
        # Sort by chunk_index if available, concatenate text
        sorted_points = sorted(points, key=lambda p: p.payload.get("chunk_index", 0))
        texts = []
        for point in sorted_points:
            text = point.payload.get("text", "")
            if text:
                texts.append(text)
        
        combined = "\n\n".join(texts)
        return combined[:max_chars]
        
    except Exception as e:
        logger.warning(f"Failed to fetch chunks from Qdrant for {doc_id}: {e}")
        return ""


async def classify_and_update_document(
    doc_id: str,
    metadata: dict,
    project_id: str = "",
    dry_run: bool = False,
) -> Optional[dict]:
    """
    Classify a document and update its metadata.
    
    Args:
        doc_id: Document UUID
        metadata: Current document metadata
        project_id: RAG project ID (for Qdrant collection lookup)
        dry_run: If True, don't actually update the database
        
    Returns:
        Updated metadata dict, or None if classification failed
    """
    from src.auth import get_supabase_client
    
    title = metadata.get("title", "")
    abstract = metadata.get("abstract") or ""
    qdrant_doc_id = metadata.get("doc_id", "")  # doc_id used in Qdrant
    
    # If no abstract, fetch text from Qdrant chunks
    if not abstract and qdrant_doc_id and project_id:
        logger.info(f"No abstract for {title[:40]}..., fetching from Qdrant")
        abstract = await get_document_text_from_qdrant(qdrant_doc_id, project_id, max_chars=8000)
        if abstract:
            logger.info(f"  → Got {len(abstract)} chars from Qdrant chunks")
    
    if not title and not abstract:
        logger.warning(f"Document {doc_id} has no title or abstract for classification")
        return None
    
    # Classify
    design, confidence, reasoning = await classify_study_design(title, abstract)
    
    # Update metadata
    updated_metadata = {
        **metadata,
        "study_design": design.value,
        "study_design_confidence": confidence,
        "study_design_reasoning": reasoning,
    }
    
    if dry_run:
        logger.info(f"[DRY RUN] Would update {doc_id}: study_design={design.value}")
        return updated_metadata
    
    # Save to database
    try:
        client = get_supabase_client()
        client.table("documents").update({
            "metadata": updated_metadata
        }).eq("id", doc_id).execute()
        
        logger.info(f"Updated document {doc_id} with study_design={design.value}")
        return updated_metadata
        
    except Exception as e:
        logger.error(f"Failed to update document {doc_id}: {e}")
        return None


async def batch_classify_project(
    project_id: str,
    force_reclassify: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Classify all documents in a project.
    
    Args:
        project_id: RAG project UUID
        force_reclassify: If True, reclassify even if already classified
        dry_run: If True, don't actually update the database
        
    Returns:
        Summary dict with counts
    """
    from src.auth import get_supabase_client
    
    client = get_supabase_client()
    
    # Get all documents
    result = client.table("documents").select("id, metadata").eq("rag_project_id", project_id).execute()
    documents = result.data or []
    
    logger.info(f"Found {len(documents)} documents in project {project_id}")
    
    stats = {
        "total": len(documents),
        "classified": 0,
        "skipped": 0,
        "failed": 0,
        "by_design": {},
    }
    
    for doc in documents:
        doc_id = doc["id"]
        metadata = doc.get("metadata", {}) or {}
        
        # Skip if already classified (unless force)
        if metadata.get("study_design") and not force_reclassify:
            stats["skipped"] += 1
            design = metadata["study_design"]
            stats["by_design"][design] = stats["by_design"].get(design, 0) + 1
            continue
        
        # Classify (pass project_id for Qdrant lookup)
        updated = await classify_and_update_document(
            doc_id, metadata, project_id=project_id, dry_run=dry_run
        )
        
        if updated:
            stats["classified"] += 1
            design = updated.get("study_design", "unknown")
            stats["by_design"][design] = stats["by_design"].get(design, 0) + 1
        else:
            stats["failed"] += 1
    
    logger.info(f"Classification complete: {stats}")
    return stats
