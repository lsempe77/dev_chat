"""
DevChat v2.0 SOTA - Knowledge Graph Connection

Neo4j connection manager for graph-based retrieval.
"""

import os
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from src.config.settings import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Optional neo4j import (only needed if graph features enabled)
try:
    from neo4j import AsyncGraphDatabase, AsyncDriver
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    logger.info("neo4j package not installed - knowledge graph features disabled")


class Neo4jConnection:
    """
    Async Neo4j connection manager.
    
    Provides connection pooling and query execution.
    """
    
    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        Initialize Neo4j connection.
        
        Args:
            uri: Neo4j URI (bolt://localhost:7687)
            user: Neo4j username
            password: Neo4j password
        """
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "")
        self._driver: Optional["AsyncDriver"] = None
        
    async def connect(self) -> bool:
        """
        Establish connection to Neo4j.
        
        Returns:
            True if connected successfully
        """
        if not NEO4J_AVAILABLE:
            logger.warning("Neo4j package not installed")
            return False
            
        if not self.password:
            logger.warning("NEO4J_PASSWORD not set - knowledge graph disabled")
            return False
        
        try:
            self._driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
            )
            # Verify connection
            await self._driver.verify_connectivity()
            logger.info(f"Connected to Neo4j at {self.uri}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            return False
    
    async def close(self):
        """Close the connection."""
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")
    
    async def execute(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query.
        
        Args:
            query: Cypher query string
            parameters: Query parameters
            
        Returns:
            List of result records as dictionaries
        """
        if not self._driver:
            raise RuntimeError("Not connected to Neo4j")
        
        async with self._driver.session() as session:
            result = await session.run(query, parameters or {})
            records = await result.data()
            return records
    
    async def execute_write(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a write transaction.
        
        Args:
            query: Cypher query string
            parameters: Query parameters
            
        Returns:
            Summary of the transaction
        """
        if not self._driver:
            raise RuntimeError("Not connected to Neo4j")
        
        async with self._driver.session() as session:
            result = await session.run(query, parameters or {})
            summary = await result.consume()
            return {
                "nodes_created": summary.counters.nodes_created,
                "relationships_created": summary.counters.relationships_created,
                "properties_set": summary.counters.properties_set,
            }


# Global connection instance
_connection: Optional[Neo4jConnection] = None


async def get_neo4j_connection() -> Optional[Neo4jConnection]:
    """Get or create the global Neo4j connection."""
    global _connection
    
    if not settings.knowledge_graph_enabled:
        return None
    
    if _connection is None:
        _connection = Neo4jConnection()
        connected = await _connection.connect()
        if not connected:
            _connection = None
    
    return _connection


async def init_neo4j():
    """Initialize Neo4j connection at app startup."""
    if settings.knowledge_graph_enabled:
        await get_neo4j_connection()


async def close_neo4j():
    """Close Neo4j connection at app shutdown."""
    global _connection
    if _connection:
        await _connection.close()
        _connection = None
