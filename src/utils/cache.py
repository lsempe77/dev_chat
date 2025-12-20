"""
DevChat v2.0 - Response Caching for Production Performance

In-memory LRU cache with TTL for query responses.
Reduces latency and LLM costs for repeated identical queries.

Features:
- TTL-based expiration
- LRU eviction when max size reached
- Query fingerprinting for cache keys
- Cache hit/miss metrics

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

from src.config.settings import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """Single cache entry with TTL tracking."""
    value: Any
    created_at: float
    ttl_seconds: float
    hit_count: int = 0
    
    @property
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() - self.created_at > self.ttl_seconds
    
    def touch(self):
        """Record a cache hit."""
        self.hit_count += 1


class ResponseCache:
    """
    Thread-safe LRU cache with TTL for query responses.
    
    Args:
        max_size: Maximum number of entries to store
        ttl_seconds: Time-to-live for entries (from settings by default)
        enabled: Whether caching is enabled (from settings by default)
    """
    
    def __init__(
        self,
        max_size: int = 100,
        ttl_seconds: Optional[int] = None,
        enabled: Optional[bool] = None,
    ):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds or settings.response_cache_ttl_seconds
        self.enabled = enabled if enabled is not None else settings.enable_response_cache
        
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        
        # Metrics
        self._hits = 0
        self._misses = 0
    
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
    ) -> Optional[Any]:
        """
        Get cached response if available and not expired.
        
        Returns:
            Cached response or None if not found/expired
        """
        if not self.enabled:
            return None
        
        key = self._generate_key(query, filters, settings_dict)
        
        async with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            entry = self._cache[key]
            
            # Check expiration
            if entry.is_expired:
                del self._cache[key]
                self._misses += 1
                logger.debug(f"Cache expired for key {key}")
                return None
            
            # Move to end (LRU)
            self._cache.move_to_end(key)
            entry.touch()
            self._hits += 1
            
            logger.debug(f"Cache hit for key {key} (hits: {entry.hit_count})")
            return entry.value
    
    async def set(
        self,
        query: str,
        response: Any,
        filters: Optional[List[Dict]] = None,
        settings_dict: Optional[Dict] = None,
    ):
        """
        Store response in cache.
        
        Evicts oldest entries if max_size exceeded.
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
            
            # Store new entry
            self._cache[key] = CacheEntry(
                value=response,
                created_at=time.time(),
                ttl_seconds=self.ttl_seconds,
            )
            
            logger.debug(f"Cache stored for key {key} (size: {len(self._cache)})")
    
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
        
        return {
            "enabled": self.enabled,
            "size": len(self._cache),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 3),
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
