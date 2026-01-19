"""
Simple in-memory caching for the Quote Engine API.

Provides request-level caching to avoid recomputing identical quotes.
"""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from dataclasses import dataclass
from collections import OrderedDict
import threading


@dataclass
class CacheEntry:
    """A single cache entry."""
    key: str
    value: Any
    created_at: datetime
    expires_at: datetime
    hits: int = 0


class QuoteCache:
    """
    LRU cache for quote results.

    Features:
    - Time-based expiration
    - LRU eviction when max size reached
    - Thread-safe operations
    - Hit/miss statistics
    """

    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: int = 3600,  # 1 hour default
    ):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def _make_key(self, params: Dict[str, Any]) -> str:
        """Create a cache key from request parameters."""
        # Sort keys for consistent hashing
        sorted_params = json.dumps(params, sort_keys=True, default=str)
        return hashlib.md5(sorted_params.encode()).hexdigest()

    def get(self, params: Dict[str, Any]) -> Optional[Any]:
        """
        Get a cached value.

        Args:
            params: Request parameters

        Returns:
            Cached value or None if not found/expired
        """
        key = self._make_key(params)

        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]

            # Check expiration
            if datetime.now() > entry.expires_at:
                del self._cache[key]
                self._misses += 1
                return None

            # Update hit count and move to end (LRU)
            entry.hits += 1
            self._cache.move_to_end(key)
            self._hits += 1

            return entry.value

    def set(self, params: Dict[str, Any], value: Any) -> None:
        """
        Cache a value.

        Args:
            params: Request parameters
            value: Value to cache
        """
        key = self._make_key(params)
        now = datetime.now()

        with self._lock:
            # Remove oldest entries if at capacity
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)

            self._cache[key] = CacheEntry(
                key=key,
                value=value,
                created_at=now,
                expires_at=now + timedelta(seconds=self.ttl_seconds),
            )

    def invalidate(self, params: Optional[Dict[str, Any]] = None) -> int:
        """
        Invalidate cache entries.

        Args:
            params: Specific entry to invalidate, or None for all

        Returns:
            Number of entries invalidated
        """
        with self._lock:
            if params is None:
                count = len(self._cache)
                self._cache.clear()
                return count

            key = self._make_key(params)
            if key in self._cache:
                del self._cache[key]
                return 1
            return 0

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries.

        Returns:
            Number of entries removed
        """
        now = datetime.now()
        removed = 0

        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if now > entry.expires_at
            ]
            for key in expired_keys:
                del self._cache[key]
                removed += 1

        return removed

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0

            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'ttl_seconds': self.ttl_seconds,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate_pct': round(hit_rate, 2),
                'total_requests': total_requests,
            }


# Global cache instance
quote_cache = QuoteCache(max_size=1000, ttl_seconds=3600)


def get_cached_quote(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Get a quote from cache."""
    return quote_cache.get(params)


def cache_quote(params: Dict[str, Any], result: Dict[str, Any]) -> None:
    """Cache a quote result."""
    quote_cache.set(params, result)


def invalidate_cache() -> int:
    """Invalidate all cached quotes."""
    return quote_cache.invalidate()


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics."""
    return quote_cache.stats()
