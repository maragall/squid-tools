"""Memory-bounded LRU cache for numpy arrays.

Evicts by nbytes (not item count) to bound actual RAM usage.
Pattern from ndviewer_light, proven in production.
"""

from __future__ import annotations

import threading
from collections import OrderedDict

import numpy as np


class MemoryBoundedLRUCache:
    """Thread-safe LRU cache bounded by total memory in bytes.

    Items larger than max_bytes are silently rejected (not cached).
    """

    def __init__(self, max_bytes: int = 256 * 1024 * 1024) -> None:
        self._max_bytes = max_bytes
        self._current_bytes = 0
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def current_bytes(self) -> int:
        return self._current_bytes

    def get(self, key: str) -> np.ndarray | None:
        """Get item from cache. Returns None on miss. Updates recency on hit."""
        with self._lock:
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return self._cache[key]

    def put(self, key: str, value: np.ndarray) -> None:
        """Add item to cache. Evicts LRU entries if over budget.

        Items larger than max_bytes are silently rejected.
        """
        item_bytes = value.nbytes
        if item_bytes > self._max_bytes:
            return

        with self._lock:
            # Remove existing entry if updating
            if key in self._cache:
                self._current_bytes -= self._cache[key].nbytes
                del self._cache[key]

            # Evict LRU entries until there's room
            while self._current_bytes + item_bytes > self._max_bytes and self._cache:
                _, evicted = self._cache.popitem(last=False)
                self._current_bytes -= evicted.nbytes

            self._cache[key] = value
            self._current_bytes += item_bytes

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._current_bytes = 0
