"""
DevChat v2.0 SOTA - Chunking Strategies

Implements structure-aware chunking:
- Semantic chunking (split by meaning)
- Parent-child indexing (small chunks for retrieval, large for context)
- Markdown-aware splitting (preserve headers, tables, lists)
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

from llama_index.core.node_parser import (
    MarkdownNodeParser,
    SentenceSplitter,
    SemanticSplitterNodeParser,
)
from llama_index.core.schema import BaseNode, Document, TextNode

from src.config.settings import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class BaseChunker(ABC):
    """Abstract base class for chunking strategies."""
    
    @abstractmethod
    def chunk(self, documents: List[Document]) -> List[BaseNode]:
        """
        Split documents into chunks.
        
        Args:
            documents: List of documents to chunk
            
        Returns:
            List of nodes (chunks) with metadata
        """
        pass


class SimpleChunker(BaseChunker):
    """
    Basic sentence-based chunking.
    
    Good for: Quick prototyping, simple documents
    Not ideal for: Complex academic papers with tables/figures
    """
    
    def __init__(
        self,
        chunk_size: int = settings.chunk_size,
        chunk_overlap: int = settings.chunk_overlap,
    ):
        self.parser = SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    
    def chunk(self, documents: List[Document]) -> List[BaseNode]:
        """Split documents using sentence-based chunking."""
        nodes = self.parser.get_nodes_from_documents(documents)
        logger.info(f"SimpleChunker produced {len(nodes)} chunks from {len(documents)} docs")
        return nodes


class MarkdownChunker(BaseChunker):
    """
    Markdown-aware chunking that preserves document structure.
    
    - Respects header hierarchy
    - Keeps code blocks intact
    - Preserves list structure
    """
    
    def __init__(self):
        self.parser = MarkdownNodeParser()
        self.fallback_splitter = SentenceSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
    
    def chunk(self, documents: List[Document]) -> List[BaseNode]:
        """Split documents respecting markdown structure."""
        # First pass: markdown-aware splitting
        md_nodes = self.parser.get_nodes_from_documents(documents)
        
        # Second pass: further split any oversized nodes
        final_nodes = []
        for node in md_nodes:
            if len(node.text) > settings.chunk_size * 2:
                # Split large nodes further
                sub_doc = Document(text=node.text, metadata=node.metadata)
                sub_nodes = self.fallback_splitter.get_nodes_from_documents([sub_doc])
                # Preserve parent metadata
                for sub_node in sub_nodes:
                    sub_node.metadata.update(node.metadata)
                final_nodes.extend(sub_nodes)
            else:
                final_nodes.append(node)
        
        logger.info(f"MarkdownChunker produced {len(final_nodes)} chunks from {len(documents)} docs")
        return final_nodes


class SemanticChunker(BaseChunker):
    """
    Semantic chunking - splits based on meaning, not fixed size.
    
    Uses embeddings to detect topic boundaries.
    Best for: Academic papers where sections have distinct topics.
    
    Requires: Embedding model for semantic similarity
    """
    
    def __init__(
        self,
        embed_model=None,
        breakpoint_percentile: int = 95,
        buffer_size: int = 1,
    ):
        """
        Initialize semantic chunker.
        
        Args:
            embed_model: Embedding model for similarity calculation
            breakpoint_percentile: Threshold for detecting topic changes
            buffer_size: Number of sentences to consider together
        """
        if embed_model is None:
            # Lazy import to avoid circular dependencies
            from src.ingestion.embeddings import EmbeddingGenerator
            embed_model = EmbeddingGenerator().get_embed_model()
        
        self.parser = SemanticSplitterNodeParser(
            embed_model=embed_model,
            breakpoint_percentile_threshold=breakpoint_percentile,
            buffer_size=buffer_size,
        )
        
    def chunk(self, documents: List[Document]) -> List[BaseNode]:
        """Split documents based on semantic boundaries."""
        nodes = self.parser.get_nodes_from_documents(documents)
        logger.info(f"SemanticChunker produced {len(nodes)} chunks from {len(documents)} docs")
        return nodes


class ParentChildChunker(BaseChunker):
    """
    Parent-child chunking strategy.
    
    Creates two levels of chunks:
    - Small chunks (child): Used for precise retrieval
    - Large chunks (parent): Used for synthesis context
    
    When a child chunk is retrieved, the parent is fetched for context.
    """
    
    def __init__(
        self,
        child_chunk_size: int = settings.chunk_size,
        child_chunk_overlap: int = settings.chunk_overlap,
        parent_chunk_size: int = settings.parent_chunk_size,
    ):
        self.child_chunk_size = child_chunk_size
        self.child_chunk_overlap = child_chunk_overlap
        self.parent_chunk_size = parent_chunk_size
        
        self.parent_splitter = SentenceSplitter(
            chunk_size=parent_chunk_size,
            chunk_overlap=50,
        )
        self.child_splitter = SentenceSplitter(
            chunk_size=child_chunk_size,
            chunk_overlap=child_chunk_overlap,
        )
    
    def chunk(self, documents: List[Document]) -> Tuple[List[BaseNode], List[BaseNode], Dict]:
        """
        Create parent and child chunks with linkage.
        
        Returns:
            Tuple of (child_nodes, parent_nodes, child_to_parent_map)
        """
        parent_nodes = []
        child_nodes = []
        child_to_parent: Dict[str, str] = {}
        
        for doc in documents:
            # Create parent chunks
            doc_parents = self.parent_splitter.get_nodes_from_documents([doc])
            
            for parent in doc_parents:
                parent_id = parent.node_id
                parent_nodes.append(parent)
                
                # Create child chunks from each parent
                parent_doc = Document(text=parent.text, metadata=parent.metadata)
                doc_children = self.child_splitter.get_nodes_from_documents([parent_doc])
                
                for child in doc_children:
                    # Add parent reference to child metadata
                    child.metadata["parent_id"] = parent_id
                    child.metadata["parent_text"] = parent.text[:500]  # Preview
                    child_nodes.append(child)
                    child_to_parent[child.node_id] = parent_id
        
        logger.info(
            f"ParentChildChunker produced {len(child_nodes)} child chunks "
            f"and {len(parent_nodes)} parent chunks from {len(documents)} docs"
        )
        
        return child_nodes, parent_nodes, child_to_parent
    
    def chunk_with_storage(
        self,
        documents: List[Document],
    ) -> List[BaseNode]:
        """
        Chunk documents and return only child nodes.
        
        Parent information is stored in metadata for later retrieval.
        """
        child_nodes, parent_nodes, mapping = self.chunk(documents)
        
        # Create a parent lookup dict
        parent_lookup = {p.node_id: p.text for p in parent_nodes}
        
        # Enrich child nodes with full parent text reference
        for child in child_nodes:
            parent_id = child.metadata.get("parent_id")
            if parent_id and parent_id in parent_lookup:
                # Store parent text for later expansion
                child.metadata["parent_text_full"] = parent_lookup[parent_id]
        
        return child_nodes


class HybridChunker(BaseChunker):
    """
    Combines multiple chunking strategies.
    
    1. First applies markdown-aware parsing
    2. Then applies parent-child chunking
    3. Optionally applies semantic refinement
    """
    
    def __init__(
        self,
        use_semantic: bool = settings.use_semantic_chunking,
        embed_model=None,
    ):
        self.use_semantic = use_semantic
        self.markdown_chunker = MarkdownChunker()
        self.parent_child_chunker = ParentChildChunker()
        self.semantic_chunker = None
        
        if use_semantic and embed_model:
            self.semantic_chunker = SemanticChunker(embed_model=embed_model)
    
    def chunk(self, documents: List[Document]) -> List[BaseNode]:
        """Apply hybrid chunking strategy."""
        # Step 1: Markdown-aware parsing
        md_nodes = self.markdown_chunker.chunk(documents)
        logger.info(f"After markdown parsing: {len(md_nodes)} nodes")
        
        # Convert nodes back to documents for further processing
        intermediate_docs = [
            Document(text=n.text, metadata=n.metadata)
            for n in md_nodes
        ]
        
        # Step 2: Parent-child chunking
        final_nodes = self.parent_child_chunker.chunk_with_storage(intermediate_docs)
        logger.info(f"After parent-child chunking: {len(final_nodes)} nodes")
        
        return final_nodes


def get_chunker(strategy: str = "hybrid") -> BaseChunker:
    """
    Factory function to get a chunker by strategy name.
    
    Args:
        strategy: One of "simple", "markdown", "semantic", "parent_child", "hybrid"
        
    Returns:
        Chunker instance
    """
    chunkers = {
        "simple": SimpleChunker,
        "markdown": MarkdownChunker,
        "semantic": SemanticChunker,
        "parent_child": ParentChildChunker,
        "hybrid": HybridChunker,
    }
    
    if strategy not in chunkers:
        logger.warning(f"Unknown chunker strategy '{strategy}', using 'hybrid'")
        strategy = "hybrid"
    
    return chunkers[strategy]()
