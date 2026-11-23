"""
tests/test_cache.py
Verification tests for MemoryLRUCache, bounded memory guards, and namespace invalidation.
"""

import time
import pytest
from src.storage.cache import MemoryLRUCache, cached_api_call


def test_cache_basic_get_set():
    cache = MemoryLRUCache(max_items=10, max_bytes=10000, default_ttl=5.0)
    cache.set("foo", {"bar": 123})
    assert cache.get("foo") == {"bar": 123}
    assert cache.get("nonexistent") is None


def test_cache_ttl_expiration():
    cache = MemoryLRUCache(max_items=10, max_bytes=10000, default_ttl=0.1)
    cache.set("fast_expire", "val", ttl=0.05)
    assert cache.get("fast_expire") == "val"
    time.sleep(0.06)
    assert cache.get("fast_expire") is None


def test_cache_lru_item_eviction():
    cache = MemoryLRUCache(max_items=3, max_bytes=10000, default_ttl=10.0)
    cache.set("k1", "v1")
    cache.set("k2", "v2")
    cache.set("k3", "v3")

    # Access k1 to make it most recently used
    assert cache.get("k1") == "v1"

    # Add k4; k2 should be evicted (as k1 was accessed and k3 is newer)
    cache.set("k4", "v4")
    assert cache.get("k2") is None
    assert cache.get("k1") == "v1"
    assert cache.get("k3") == "v3"
    assert cache.get("k4") == "v4"


def test_cache_namespace_invalidation():
    cache = MemoryLRUCache(max_items=10, max_bytes=10000, default_ttl=10.0)
    cache.set("screener:top", [1, 2, 3])
    cache.set("screener:bottom", [4, 5, 6])
    cache.set("tearsheet:RELIANCE", {"pe": 25.0})

    deleted = cache.clear_namespace("screener:")
    assert deleted == 2
    assert cache.get("screener:top") is None
    assert cache.get("screener:bottom") is None
    assert cache.get("tearsheet:RELIANCE") == {"pe": 25.0}


def test_cache_stats():
    cache = MemoryLRUCache(max_items=10, max_bytes=10000, default_ttl=10.0)
    cache.set("a", "b")
    cache.get("a") # hit
    cache.get("x") # miss
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["items_count"] == 1
    assert stats["hit_ratio_pct"] == 50.0
