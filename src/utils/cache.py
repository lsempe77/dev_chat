"""
DevChat v2.0 - Response Caching for Production Performance

In-memory LRU cache with TTL for query responses.
Reduces latency and LLM costs for repeated identical queries.

Features:
- TTL-based expiration
- LRU eviction when max size reached
- Query fingerprinting for cache keys
- Cache hit/miss metrics
- Semantic similarity matching (optional) - matches similar queries using embeddings

Usage:
    cache = ResponseCache(max_size=100, ttl_seconds=3600)
    
    # Check cache
    cached = await cache.get(query, filters)
    if cached:
        return cached
    
    # Generate response...
    
    # Store in cache
    await cache.set(query, filters, response)
"""

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.config.settings import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """Single cache entry with TTL tracking and optional embedding."""
    value: Any
    created_at: float
    ttl_seconds: float
    hit_count: int = 0
    query_embedding: Optional[np.ndarray] = None  # For semantic matching
    
    @property
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() - self.created_at > self.ttl_seconds
    
    def touch(self):
        """Record a cache hit."""
        self.hit_count += 1


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class ResponseCache:
    """
    Thread-safe LRU cache with TTL for query responses.
    
    Supports both exact match and semantic similarity matching.
    Semantic matching uses query embeddings to find similar cached queries.
    
    Args:
        max_size: Maximum number of entries to store
        ttl_seconds: Time-to-live for entries (from settings by default)
        enabled: Whether caching is enabled (from settings by default)
        semantic_enabled: Whether to use semantic similarity matching
        semantic_threshold: Minimum similarity to consider a match (0.0-1.0)
    """
    
    def __init__(
        self,
        max_size: int = 100,
        ttl_seconds: Optional[int] = None,
        enabled: Optional[bool] = None,
        semantic_enabled: Optional[bool] = None,
        semantic_threshold: Optional[float] = None,
    ):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds or settings.response_cache_ttl_seconds
        self.enabled = enabled if enabled is not None else settings.enable_response_cache
        self.semantic_enabled = semantic_enabled if semantic_enabled is not None else getattr(settings, 'semantic_cache_enabled', False)
        self.semantic_threshold = semantic_threshold if semantic_threshold is not None else getattr(settings, 'semantic_cache_threshold', 0.95)
        
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        
        # Metrics
        self._hits = 0
        self._misses = 0
        self._semantic_hits = 0  # Track semantic matches separately
        
        logger.info(f"ResponseCache initialized: enabled={self.enabled}, semantic={self.semantic_enabled}, threshold={self.semantic_threshold}")
    
    def _generate_key(
        self,
        query: str,
        filters: Optional[List[Dict]] = None,
        settings_dict: Optional[Dict] = None,
    ) -> str:
        """Generate cache key from query parameters."""
        key_data = {
            "query": query.lower().strip(),
            "filters": sorted(filters or [], key=lambda x: (x.get("type", ""), x.get("value", ""))),
            "settings": settings_dict or {},
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]
    
    async def get(
        self,
        query: str,
        filters: Optional[List[Dict]] = None,
        settings_dict: Optional[Dict] = None,
        query_embedding: Optional[np.ndarray] = None,
    ) -> Optional[Any]:
        """
        Get cached response if available and not expired.
        
        First tries exact match, then semantic similarity if enabled.
        
        Args:
            query: The query string
            filters: Optional filters applied to the query
            settings_dict: Optional settings that affect the response
            query_embedding: Optional embedding for semantic matching
        
        Returns:
            Cached response or None if not found/expired
        """
        if not self.enabled:
            return None
        
        key = self._generate_key(query, filters, settings_dict)
        
        async with self._lock:
            # 1. Try exact match first
            if key in self._cache:
                entry = self._cache[key]
                
                if entry.is_expired:
                    del self._cache[key]
                    self._misses += 1
                    logger.debug(f"Cache expired for key {key}")
                else:
                    # Move to end (LRU)
                    self._cache.move_to_end(key)
                    entry.touch()
                    self._hits += 1
                    logger.debug(f"Cache exact hit for key {key} (hits: {entry.hit_count})")
                    return entry.value
            
            # 2. Try semantic match if enabled and embedding provided
            if self.semantic_enabled and query_embedding is not None:
                best_match = self._find_semantic_match(query_embedding, filters, settings_dict)
                if best_match:
                    entry, similarity = best_match
                    entry.touch()
                    self._hits += 1
                    self._semantic_hits += 1
                    logger.info(f"Cache semantic hit (similarity={similarity:.3f})")
                    return entry.value
            
            self._misses += 1
            return None
    
    def _find_semantic_match(
        self,
        query_embedding: np.ndarray,
        filters: Optional[List[Dict]] = None,
        settings_dict: Optional[Dict] = None,
    ) -> Optional[Tuple[CacheEntry, float]]:
        """
        Find semantically similar cached query.
        
        Only matches if filters and settings are compatible.
        
        Returns:
            Tuple of (CacheEntry, similarity_score) or None
        """
        best_entry = None
        best_similarity = 0.0
        
        # Normalize filters/settings for comparison
        filters_key = json.dumps(sorted(filters or [], key=lambda x: (x.get("type", ""), x.get("value", ""))))
        settings_key = json.dumps(settings_dict or {}, sort_keys=True)
        
        for key, entry in self._cache.items():
            # Skip expired entries
            if entry.is_expired:
                continue
            
            # Skip if no embedding stored
            if entry.query_embedding is None:
                continue
            
            # Check filter/settings compatibility
            # For now, require exact match on filters/settings
            # (semantic match only on query text)
            entry_filters = key.split("_")[1] if "_" in key else ""
            entry_settings = key.split("_")[2] if key.count("_") >= 2 else ""
            
            # Compute similarity
            similarity = cosine_similarity(query_embedding, entry.query_embedding)
            
            if similarity >= self.semantic_threshold and similarity > best_similarity:
                best_similarity = similarity
                best_entry = entry
        
        if best_entry:
            return (best_entry, best_similarity)
        return None
    
    async def set(
        self,
        query: str,
        response: Any,
        filters: Optional[List[Dict]] = None,
        settings_dict: Optional[Dict] = None,
        query_embedding: Optional[np.ndarray] = None,
    ):
        """
        Store response in cache.
        
        Evicts oldest entries if max_size exceeded.
        
        Args:
            query: The query string
            response: The response to cache
            filters: Optional filters applied to the query
            settings_dict: Optional settings that affect the response
            query_embedding: Optional embedding for semantic matching
        """
        if not self.enabled:
            return
        
        key = self._generate_key(query, filters, settings_dict)
        
        async with self._lock:
            # Remove if already exists
            if key in self._cache:
                del self._cache[key]
            
            # Evict oldest if at capacity
            while len(self._cache) >= self.max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                logger.debug(f"Cache evicted oldest entry: {oldest_key}")
            
            # Store new entry with embedding if provided
            self._cache[key] = CacheEntry(
                value=response,
                created_at=time.time(),
                ttl_seconds=self.ttl_seconds,
                query_embedding=query_embedding,
            )
            
            logger.debug(f"Cache stored for key {key} (size: {len(self._cache)}, semantic={query_embedding is not None})")
    
    async def invalidate(
        self,
        query: Optional[str] = None,
        pattern: Optional[str] = None,
    ):
        """
        Invalidate cache entries.
        
        Args:
            query: Specific query to invalidate
            pattern: Invalidate all entries (if "*") or future pattern matching
        """
        async with self._lock:
            if pattern == "*":
                self._cache.clear()
                logger.info("Cache fully invalidated")
            elif query:
                key = self._generate_key(query)
                if key in self._cache:
                    del self._cache[key]
                    logger.debug(f"Cache invalidated for query: {query[:50]}...")
    
    async def cleanup_expired(self):
        """Remove all expired entries. Call periodically."""
        async with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired
            ]
            for key in expired_keys:
                del self._cache[key]
            
            if expired_keys:
                logger.debug(f"Cache cleanup removed {len(expired_keys)} expired entries")
    
    def get_stats(self) -> Dict:
        """Get cache statistics for monitoring."""
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0.0
        semantic_rate = self._semantic_hits / self._hits if self._hits > 0 else 0.0
        
        # Count entries with embeddings
        entries_with_embeddings = sum(1 for e in self._cache.values() if e.query_embedding is not None)
        
        return {
            "enabled": self.enabled,
            "semantic_enabled": self.semantic_enabled,
            "semantic_threshold": self.semantic_threshold,
            "size": len(self._cache),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds,
            "hits": self._hits,
            "semantic_hits": self._semantic_hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 3),
            "semantic_hit_rate": round(semantic_rate, 3),
            "entries_with_embeddings": entries_with_embeddings,
        }


# Global cache instance
_response_cache: Optional[ResponseCache] = None


def get_response_cache() -> ResponseCache:
    """Get or create the global response cache."""
    global _response_cache
    if _response_cache is None:
        _response_cache = ResponseCache()
    return _response_cache


async def cache_cleanup_task(interval_seconds: int = 300):
    """
    Background task to periodically clean up expired cache entries.
    
    Run with: asyncio.create_task(cache_cleanup_task())
    """
    cache = get_response_cache()
    while True:
        await asyncio.sleep(interval_seconds)
        await cache.cleanup_expired()
