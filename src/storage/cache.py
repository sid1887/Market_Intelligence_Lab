"""
src/storage/cache.py
Unified High-Performance In-Memory Multi-Tier Cache Layer (ADR-0011).
Enforces thread-safety, strict TTL expiry, memory bounds (< 30 MB RAM),
and microsecond-latency hit resolution for API hot paths.
"""

import time
import os
import gc
import json
import gzip
import logging
import resource
import threading
from collections import OrderedDict
from typing import Any, Optional, Dict, Tuple, Callable
from functools import wraps

logger = logging.getLogger("MIL.Cache")


def get_current_process_rss_mb() -> float:
    """Reads current live resident set size in MB from /proc/self/status or getrusage."""
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return float(line.split()[1]) / 1024.0
    except Exception:
        pass
    try:
        # On Linux, ru_maxrss is in KiB
        return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0
    except Exception:
        return 0.0


_MEMORY_GUARD_HOOKS: list = []


def register_memory_guard_hook(hook_fn) -> None:
    """Registers an external cache-eviction callback invoked when RSS exceeds threshold."""
    if callable(hook_fn) and hook_fn not in _MEMORY_GUARD_HOOKS:
        _MEMORY_GUARD_HOOKS.append(hook_fn)


def enforce_rss_memory_guard(threshold_mb: float = 375.0) -> Dict[str, Any]:
    """
    Checks process RSS memory against threshold. If exceeded, triggers emergency cache
    eviction and garbage collection to protect Render's 512 MB container against SIGKILL 137.
    """
    rss = get_current_process_rss_mb()
    evicted = False
    if rss >= threshold_mb:
        logger.warning(f"[MEMORY-GUARD] Process RSS ({rss:.1f} MB) >= {threshold_mb:.1f} MB! Evicting LRU caches.")
        app_cache.clear()
        for hook in list(_MEMORY_GUARD_HOOKS):
            try:
                hook()
            except Exception:
                pass
        gc.collect()
        try:
            import ctypes
            libc = ctypes.CDLL("libc.so.6")
            if hasattr(libc, "malloc_trim"):
                libc.malloc_trim(0)
        except Exception:
            pass
        evicted = True
        new_rss = get_current_process_rss_mb()
        logger.info(f"[MEMORY-GUARD] Emergency eviction complete. RSS: {rss:.1f} MB -> {new_rss:.1f} MB.")
        rss = new_rss

    return {
        "rss_mb": round(rss, 2),
        "threshold_mb": threshold_mb,
        "evicted": evicted,
        "memory_headroom_mb": round(max(0.0, 512.0 - rss), 2)
    }


class MemoryLRUCache:
    """Thread-safe bounded in-memory LRU cache with TTL expiration and memory guards."""

    def __init__(self, max_items: int = 500, max_bytes: int = 30 * 1024 * 1024, default_ttl: float = 300.0):
        self.max_items = max_items
        self.max_bytes = max_bytes
        self.default_ttl = default_ttl
        self._lock = threading.RLock()
        self._cache: OrderedDict[str, Tuple[Any, float, int]] = OrderedDict()  # key -> (value, expiry_ts, approx_bytes)
        self._current_bytes = 0
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def _estimate_size(self, val: Any) -> int:
        if isinstance(val, (bytes, bytearray)):
            return len(val)
        if isinstance(val, str):
            return len(val.encode("utf-8"))
        if isinstance(val, (dict, list)):
            return len(json.dumps(val, default=str).encode("utf-8"))
        return 128

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            val, expiry_ts, b_size = self._cache[key]
            if time.time() > expiry_ts:
                # Expired
                self._evict_key(key)
                self._misses += 1
                return None
            # Move to MRU position
            self._cache.move_to_end(key)
            self._hits += 1
            return val

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        expiry = time.time() + (ttl if ttl is not None else self.default_ttl)
        approx_bytes = self._estimate_size(value)

        with self._lock:
            if key in self._cache:
                self._evict_key(key)

            # Evict LRU items if over limit
            while (len(self._cache) >= self.max_items or (self._current_bytes + approx_bytes > self.max_bytes)) and self._cache:
                oldest_key = next(iter(self._cache))
                self._evict_key(oldest_key)
                self._evictions += 1

            self._cache[key] = (value, expiry, approx_bytes)
            self._current_bytes += approx_bytes

    def _evict_key(self, key: str) -> None:
        if key in self._cache:
            _, _, b_size = self._cache.pop(key)
            self._current_bytes = max(0, self._current_bytes - b_size)

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._cache:
                self._evict_key(key)
                return True
            return False

    def clear_namespace(self, prefix: str) -> int:
        with self._lock:
            keys_to_del = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_del:
                self._evict_key(k)
            return len(keys_to_del)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._current_bytes = 0

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total_requests = self._hits + self._misses
            hit_ratio = (self._hits / total_requests) if total_requests > 0 else 0.0
            return {
                "items_count": len(self._cache),
                "current_bytes": self._current_bytes,
                "current_mb": round(self._current_bytes / (1024 * 1024), 2),
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "hit_ratio_pct": round(hit_ratio * 100, 2)
            }


# Singleton Global App Cache
app_cache = MemoryLRUCache(max_items=1000, max_bytes=25 * 1024 * 1024, default_ttl=300.0)


def cached_api_call(namespace: str, ttl: float = 300.0, key_builder: Optional[Callable[..., str]] = None):
    """Decorator for caching API route handlers or expensive computations."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if key_builder:
                key = f"{namespace}:{key_builder(*args, **kwargs)}"
            else:
                arg_repr = "_".join(str(a) for a in args)
                kwarg_repr = "_".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
                key = f"{namespace}:{arg_repr}:{kwarg_repr}"

            cached = app_cache.get(key)
            if cached is not None:
                return cached

            result = fn(*args, **kwargs)
            if result is not None:
                app_cache.set(key, result, ttl=ttl)
            return result
        return wrapper
    return decorator
