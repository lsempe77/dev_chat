"""
DevChat v2.0 SOTA - Qdrant Indexer

Manages the Qdrant vector database:
- Collection creation with hybrid search support
- Document indexing (dense + sparse vectors)
- Metadata payload indexing
"""

from typing import Dict, List, Optional

from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from src.config.settings import settings
from src.ingestion.embeddings import EmbeddingGenerator, get_embedding_dimension
from src.utils.logging import get_logger

logger = get_logger(__name__)


class QdrantIndexer:
    """
    Manage Qdrant vector database for hybrid search.
    
    Features:
    - Dense vectors (semantic similarity)
    - Sparse vectors (BM25/keyword matching)
    - Metadata payload indexing
    """
    
    def __init__(
        self,
        url: str = settings.qdrant_url,
        api_key: Optional[str] = settings.qdrant_api_key,
        collection_name: str = settings.qdrant_collection_name,
    ):
        self.collection_name = collection_name
        
        # Initialize client
        if api_key:
            self.client = QdrantClient(url=url, api_key=api_key)
        else:
            self.client = QdrantClient(url=url)
        
        self.embedding_generator = EmbeddingGenerator()
        self.embedding_dim = get_embedding_dimension()
        
        logger.info(f"Connected to Qdrant at {url}")
    
    def create_collection(
        self,
        recreate: bool = False,
        enable_hybrid: bool = settings.hybrid_enabled,
    ) -> None:
        """
        Create or recreate the Qdrant collection.
        
        Args:
            recreate: If True, delete existing collection first
            enable_hybrid: If True, configure for hybrid search
        """
        # Check if collection exists
        try:
            collection_info = self.client.get_collection(self.collection_name)
            if collection_info and not recreate:
                logger.info(f"Collection '{self.collection_name}' already exists")
                return
            elif collection_info and recreate:
                logger.warning(f"Deleting existing collection '{self.collection_name}'")
                self.client.delete_collection(self.collection_name)
        except UnexpectedResponse:
            pass  # Collection doesn't exist
        
        # Configure vectors
        vectors_config = {
            "dense": models.VectorParams(
                size=self.embedding_dim,
                distance=models.Distance.COSINE,
            )
        }
        
        # Configure sparse vectors for hybrid search
        sparse_vectors_config = None
        if enable_hybrid:
            sparse_vectors_config = {
                "sparse": models.SparseVectorParams(
                    modifier=models.Modifier.IDF,  # BM25-like scoring
                )
            }
        
        # Create collection
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=vectors_config,
            sparse_vectors_config=sparse_vectors_config,
            optimizers_config=models.OptimizersConfigDiff(
                indexing_threshold=20000,
            ),
        )
        
        # Create payload indexes for metadata filtering
        self._create_payload_indexes()
        
        logger.info(
            f"Created collection '{self.collection_name}' "
            f"(hybrid={enable_hybrid}, dim={self.embedding_dim})"
        )
    
    def _create_payload_indexes(self) -> None:
        """Create indexes on metadata fields for efficient filtering."""
        # Index commonly filtered fields
        index_fields = [
            ("study_id", models.PayloadSchemaType.KEYWORD),
            ("year", models.PayloadSchemaType.INTEGER),
            ("sector", models.PayloadSchemaType.KEYWORD),
            ("country", models.PayloadSchemaType.KEYWORD),
            ("region", models.PayloadSchemaType.KEYWORD),
            ("study_type", models.PayloadSchemaType.KEYWORD),
            ("confidence_rating", models.PayloadSchemaType.KEYWORD),
        ]
        
        for field_name, field_type in index_fields:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=field_type,
                )
            except Exception as e:
                logger.debug(f"Index for '{field_name}' may already exist: {e}")
    
    def index_nodes(
        self,
        nodes: List,
        batch_size: int = 100,
        enable_sparse: bool = settings.hybrid_enabled,
    ) -> None:
        """
        Index nodes into Qdrant.
        
        Args:
            nodes: List of LlamaIndex nodes with embeddings
            batch_size: Number of points to upsert at once
            enable_sparse: Whether to generate sparse vectors
        """
        from tqdm import tqdm
        
        # Ensure embeddings are present
        nodes_without_embeddings = [n for n in nodes if n.embedding is None]
        if nodes_without_embeddings:
            logger.info(f"Generating embeddings for {len(nodes_without_embeddings)} nodes")
            self.embedding_generator.embed_nodes(nodes_without_embeddings)
        
        # Prepare points
        points = []
        for node in tqdm(nodes, desc="Preparing points"):
            point = self._node_to_point(node, enable_sparse=enable_sparse)
            points.append(point)
        
        # Batch upsert
        for i in tqdm(range(0, len(points), batch_size), desc="Indexing batches"):
            batch = points[i:i + batch_size]
            self.client.upsert(
                collection_name=self.collection_name,
                points=batch,
            )
        
        logger.info(f"Indexed {len(points)} points to '{self.collection_name}'")
    
    def _node_to_point(
        self,
        node,
        enable_sparse: bool = True,
    ) -> models.PointStruct:
        """Convert a LlamaIndex node to a Qdrant point."""
        # Dense vector
        vectors = {
            "dense": node.embedding,
        }
        
        # Sparse vector (BM25-style)
        if enable_sparse:
            sparse_vector = self._generate_sparse_vector(node.get_content())
            vectors["sparse"] = sparse_vector
        
        # Payload (metadata)
        payload = {
            "text": node.get_content(),
            "node_id": node.node_id,
            **node.metadata,
        }
        
        return models.PointStruct(
            id=self._generate_point_id(node.node_id),
            vector=vectors,
            payload=payload,
        )
    
    def _generate_sparse_vector(self, text: str) -> models.SparseVector:
        """
        Generate a sparse vector for BM25-style matching.
        
        Uses simple term frequency for now.
        For production, consider SPLADE or learned sparse encoders.
        """
        import hashlib
        import re
        from collections import Counter
        
        # Simple tokenization
        tokens = re.findall(r'\b\w+\b', text.lower())
        
        # Filter short tokens and stopwords
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'this',
            'that', 'these', 'those', 'it', 'its', 'as', 'if', 'then', 'than',
        }
        tokens = [t for t in tokens if len(t) > 2 and t not in stopwords]
        
        # Count frequencies
        freq = Counter(tokens)
        
        # Convert to sparse vector format
        # Using deterministic hash (MD5) instead of Python's randomized hash()
        indices = []
        values = []
        for token, count in freq.items():
            # Deterministic hash: MD5 -> int -> modulo
            hash_bytes = hashlib.md5(token.encode()).digest()
            idx = int.from_bytes(hash_bytes[:4], 'big') % 100000
            indices.append(idx)
            values.append(float(count))
        
        return models.SparseVector(indices=indices, values=values)
    
    def _generate_point_id(self, node_id: str) -> str:
        """Generate a valid Qdrant point ID from node ID."""
        import hashlib
        # Create a UUID-like ID from node_id
        hash_bytes = hashlib.md5(node_id.encode()).hexdigest()
        return hash_bytes
    
    def get_collection_info(self) -> Dict:
        """Get information about the collection."""
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "name": self.collection_name,
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
                "status": info.status,
            }
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return {"error": str(e)}
    
    def delete_collection(self) -> None:
        """Delete the collection."""
        try:
            self.client.delete_collection(self.collection_name)
            logger.info(f"Deleted collection '{self.collection_name}'")
        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")
    
    def delete_by_document_id(self, document_id: str) -> int:
        """
        Delete all points (chunks) associated with a document_id or source.
        
        Uses scroll to find matching points since payload fields may not be indexed.
        
        Args:
            document_id: The document ID or source filename to delete
            
        Returns:
            Number of points deleted
        """
        try:
            # Scroll through all points to find matches
            # This is safer than filter-based delete when indexes may not exist
            matching_point_ids = []
            next_offset = None
            
            while True:
                results, next_offset = self.client.scroll(
                    collection_name=self.collection_name,
                    limit=100,
                    offset=next_offset,
                    with_payload=True,
                    with_vectors=False,
                )
                
                for point in results:
                    payload = point.payload or {}
                    # Match on document_id OR source field
                    if (payload.get("document_id") == document_id or 
                        payload.get("source") == document_id or
                        payload.get("filename") == document_id):
                        matching_point_ids.append(point.id)
                
                if next_offset is None or len(results) == 0:
                    break
            
            if not matching_point_ids:
                logger.warning(f"No points found for document_id: {document_id}")
                return 0
            
            # Delete the matching points by ID
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(
                    points=matching_point_ids,
                ),
            )
            
            logger.info(f"Deleted {len(matching_point_ids)} points for document_id: {document_id}")
            return len(matching_point_ids)
            
        except Exception as e:
            logger.error(f"Failed to delete document {document_id}: {e}")
            raise
    
    def delete_by_filename(self, filename: str) -> int:
        """
        Delete all points (chunks) associated with a filename.
        
        Uses scroll to find matching points since payload fields may not be indexed.
        
        Args:
            filename: The source filename to delete
            
        Returns:
            Number of points deleted
        """
        try:
            # Scroll through all points to find matches
            matching_point_ids = []
            next_offset = None
            
            while True:
                results, next_offset = self.client.scroll(
                    collection_name=self.collection_name,
                    limit=100,
                    offset=next_offset,
                    with_payload=True,
                    with_vectors=False,
                )
                
                for point in results:
                    payload = point.payload or {}
                    source = payload.get("source", "")
                    # Match if filename is in the source path
                    if filename in source or source == filename:
                        matching_point_ids.append(point.id)
                
                if next_offset is None or len(results) == 0:
                    break
            
            if not matching_point_ids:
                logger.warning(f"No points found for filename: {filename}")
                return 0
            
            # Delete the matching points by ID
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(
                    points=matching_point_ids,
                ),
            )
            
            logger.info(f"Deleted {len(matching_point_ids)} points for filename: {filename}")
            return len(matching_point_ids)
            
        except Exception as e:
            logger.error(f"Failed to delete by filename {filename}: {e}")
            raise


class LlamaIndexQdrantAdapter:
    """
    Adapter to use Qdrant with LlamaIndex's VectorStoreIndex.
    
    Provides a cleaner integration with LlamaIndex workflows.
    """
    
    def __init__(self, indexer: Optional[QdrantIndexer] = None):
        self.indexer = indexer or QdrantIndexer()
    
    def get_vector_store(self):
        """Get a LlamaIndex-compatible vector store."""
        try:
            from llama_index.vector_stores.qdrant import QdrantVectorStore
        except ImportError:
            raise ImportError(
                "Qdrant vector store not installed. "
                "Run: pip install llama-index-vector-stores-qdrant"
            )
        
        return QdrantVectorStore(
            client=self.indexer.client,
            collection_name=self.indexer.collection_name,
            enable_hybrid=settings.hybrid_enabled,
        )
    
    def create_index(self, nodes: List):
        """Create a LlamaIndex VectorStoreIndex."""
        from llama_index.core import VectorStoreIndex, StorageContext
        
        vector_store = self.get_vector_store()
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        
        # Create index
        index = VectorStoreIndex(
            nodes=nodes,
            storage_context=storage_context,
            embed_model=self.indexer.embedding_generator.get_embed_model(),
        )
        
        return index
