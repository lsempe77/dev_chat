"""
DevChat v2.0 SOTA - Contextual Retrieval

Implements Anthropic's Contextual Retrieval technique (Sep 2024):
https://www.anthropic.com/news/contextual-retrieval

Key insight: Chunks lose context when embedded in isolation.
Solution: Prepend chunk-specific context before embedding.

Example:
  Before: "The company's revenue grew by 3% over the previous quarter."
  After: "This chunk is from an SEC filing on ACME Corp Q2 2023 performance. 
          The company's revenue grew by 3% over the previous quarter."

This reduces retrieval failures by 35-67% (with BM25 hybrid + reranking).
"""

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from llama_index.core.schema import BaseNode, Document, TextNode

from src.config.settings import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


# Cache for contextualized chunks to avoid re-processing
_context_cache: Dict[str, str] = {}


@dataclass
class ContextualizationResult:
    """Result of contextualizing a chunk."""
    original_text: str
    contextualized_text: str
    context_prefix: str
    source_document_title: str
    chunk_position: str  # e.g., "beginning", "middle", "end"


class ChunkContextualizer:
    """
    Add document-level context to chunks before embedding.
    
    This dramatically improves retrieval by giving the embedding model
    more information about what each chunk is about.
    """
    
    def __init__(
        self,
        model: str = "openai/gpt-4o-mini",  # Fast, cheap, good at summarization
        use_cache: bool = True,
    ):
        self.model = model
        self.use_cache = use_cache
        self._client = None
    
    def _get_client(self):
        """Get OpenRouter client."""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.openrouter_api_key,
            )
        return self._client
    
    def _get_cache_key(self, chunk_text: str, doc_text: str) -> str:
        """Generate cache key for chunk+document pair."""
        combined = f"{doc_text[:1000]}|{chunk_text}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    async def contextualize_chunk(
        self,
        chunk: BaseNode,
        full_document: str,
        document_metadata: Dict,
    ) -> str:
        """
        Generate context prefix for a single chunk.
        
        Args:
            chunk: The chunk to contextualize
            full_document: The full source document text
            document_metadata: Metadata about the document (title, authors, year, etc.)
            
        Returns:
            Context prefix to prepend to the chunk
        """
        chunk_text = chunk.get_content() if hasattr(chunk, 'get_content') else str(chunk)
        
        # Check cache
        if self.use_cache:
            cache_key = self._get_cache_key(chunk_text, full_document)
            if cache_key in _context_cache:
                return _context_cache[cache_key]
        
        # Build metadata string
        title = document_metadata.get('title', 'Unknown document')
        authors = document_metadata.get('authors', '')
        year = document_metadata.get('year', '')
        study_type = document_metadata.get('study_type', '')
        
        metadata_str = f"Title: {title}"
        if authors:
            metadata_str += f"\nAuthors: {authors}"
        if year:
            metadata_str += f"\nYear: {year}"
        if study_type:
            metadata_str += f"\nStudy Type: {study_type}"
        
        # Truncate document for context (keep first and last parts)
        max_doc_length = 6000
        if len(full_document) > max_doc_length:
            # Keep intro and conclusion
            doc_context = full_document[:3000] + "\n\n[...middle sections omitted...]\n\n" + full_document[-3000:]
        else:
            doc_context = full_document
        
        # Generate context using LLM
        prompt = f"""<document>
{doc_context}
</document>

<document_metadata>
{metadata_str}
</document_metadata>

<chunk>
{chunk_text}
</chunk>

Generate a short, succinct context (2-3 sentences max) to situate this chunk within the overall document. 
The context should help a search system understand what this chunk is about and connect it to the document's main topic.

Include:
- What document this is from (title, type)
- What section/topic this chunk relates to
- Any key context needed to understand the chunk

Answer ONLY with the context, nothing else. Do not repeat the chunk content."""

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.0,
            )
            
            context = response.choices[0].message.content.strip()
            
            # Cache the result
            if self.use_cache:
                _context_cache[cache_key] = context
            
            return context
            
        except Exception as e:
            logger.warning(f"Failed to generate context: {e}")
            # Fallback: use metadata as context
            return f"From '{title}' ({year}). {study_type}."
    
    async def contextualize_nodes(
        self,
        nodes: List[BaseNode],
        documents: Dict[str, Document],
        batch_size: int = 10,
        show_progress: bool = True,
    ) -> List[BaseNode]:
        """
        Contextualize all nodes by prepending document context.
        
        Args:
            nodes: List of chunks to contextualize
            documents: Dict mapping doc_id to full Document
            batch_size: Process this many concurrently
            show_progress: Show progress bar
            
        Returns:
            Nodes with contextualized text
        """
        from tqdm import tqdm
        
        contextualized_nodes = []
        
        # Group nodes by document
        nodes_by_doc: Dict[str, List[BaseNode]] = {}
        for node in nodes:
            doc_id = (
                node.metadata.get('doc_id') or
                node.metadata.get('document_id') or
                node.metadata.get('source') or
                'unknown'
            )
            if doc_id not in nodes_by_doc:
                nodes_by_doc[doc_id] = []
            nodes_by_doc[doc_id].append(node)
        
        iterator = tqdm(nodes_by_doc.items(), desc="Contextualizing") if show_progress else nodes_by_doc.items()
        
        for doc_id, doc_nodes in iterator:
            # Get the full document
            doc = documents.get(doc_id)
            if doc is None:
                # Try to find by filename
                for d_id, d in documents.items():
                    if doc_id in d_id or d_id in doc_id:
                        doc = d
                        break
            
            if doc is None:
                logger.warning(f"Document not found for doc_id: {doc_id}, using chunk metadata only")
                full_text = ""
                metadata = doc_nodes[0].metadata if doc_nodes else {}
            else:
                full_text = doc.text
                metadata = doc.metadata
            
            # Process nodes in batches
            for i in range(0, len(doc_nodes), batch_size):
                batch = doc_nodes[i:i + batch_size]
                
                # Contextualize batch concurrently
                tasks = [
                    self.contextualize_chunk(node, full_text, metadata)
                    for node in batch
                ]
                contexts = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Apply contexts to nodes
                for node, context in zip(batch, contexts):
                    if isinstance(context, Exception):
                        logger.warning(f"Context generation failed: {context}")
                        context = ""
                    
                    if context:
                        # Create new node with contextualized text
                        original_text = node.get_content()
                        contextualized_text = f"{context}\n\n{original_text}"
                        
                        new_node = TextNode(
                            text=contextualized_text,
                            metadata={
                                **node.metadata,
                                "original_text": original_text,
                                "context_prefix": context,
                                "contextualized": True,
                            },
                            id_=node.node_id,
                        )
                        contextualized_nodes.append(new_node)
                    else:
                        # Keep original node
                        contextualized_nodes.append(node)
        
        logger.info(f"Contextualized {len(contextualized_nodes)} nodes")
        return contextualized_nodes


class FastContextualizer:
    """
    Fast contextualizer that uses document metadata only.
    No LLM calls - just prepends structured metadata.
    
    Good for: Quick re-indexing, testing
    Less accurate than LLM-based contextualization.
    """
    
    def contextualize_nodes(
        self,
        nodes: List[BaseNode],
        documents: Optional[Dict[str, Document]] = None,
    ) -> List[BaseNode]:
        """
        Add metadata-based context prefix to all nodes.
        
        This is a fast alternative that doesn't require LLM calls.
        """
        contextualized_nodes = []
        
        for node in nodes:
            metadata = node.metadata
            
            # Build context from metadata
            title = metadata.get('title', 'Research document')
            year = metadata.get('year', '')
            authors = metadata.get('authors', '')
            study_type = metadata.get('study_type', '')
            sector = metadata.get('sector', '')
            country = metadata.get('country', '')
            
            # Create context prefix
            context_parts = [f"From: {title}"]
            if year:
                context_parts.append(f"Year: {year}")
            if study_type:
                context_parts.append(f"Type: {study_type}")
            if sector:
                context_parts.append(f"Sector: {sector}")
            if country:
                context_parts.append(f"Country: {country}")
            if authors:
                # Truncate long author lists
                if len(authors) > 100:
                    authors = authors[:100] + "..."
                context_parts.append(f"Authors: {authors}")
            
            context_prefix = " | ".join(context_parts)
            
            # Get section info if available
            section = metadata.get('section', '') or metadata.get('header', '')
            if section:
                context_prefix += f"\nSection: {section}"
            
            # Create contextualized node
            original_text = node.get_content()
            contextualized_text = f"[{context_prefix}]\n\n{original_text}"
            
            new_node = TextNode(
                text=contextualized_text,
                metadata={
                    **metadata,
                    "original_text": original_text,
                    "context_prefix": context_prefix,
                    "contextualized": True,
                },
                id_=node.node_id,
            )
            contextualized_nodes.append(new_node)
        
        logger.info(f"Fast-contextualized {len(contextualized_nodes)} nodes")
        return contextualized_nodes


def get_contextualizer(
    mode: str = "fast",
    **kwargs,
) -> ChunkContextualizer | FastContextualizer:
    """
    Factory function to get the appropriate contextualizer.
    
    Args:
        mode: "llm" for LLM-based, "fast" for metadata-only
        **kwargs: Additional arguments for the contextualizer
        
    Returns:
        Contextualizer instance
    """
    if mode == "llm":
        return ChunkContextualizer(**kwargs)
    else:
        return FastContextualizer()
