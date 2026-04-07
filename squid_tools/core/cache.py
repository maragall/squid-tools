"""Memory-bounded LRU cache for numpy arrays.

Pattern from ndviewer_light: evicts by nbytes, not count.
Thread-safe via threading.Lock on all operations.
"""
from __future__ import annotations

import threading
from collections import OrderedDict

import numpy as np


class MemoryBoundedLRUCache:
    """LRU cache bounded by total memory usage of cached numpy arrays."""

    def __init__(self, max_memory_bytes: int = 256 * 1024 * 1024) -> None:
        self._max_memory = max_memory_bytes
        self._current_memory = 0
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> np.ndarray | None:
        with self._lock:
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return self._cache[key]

    def put(self, key: str, value: np.ndarray) -> None:
        item_bytes = value.nbytes
        if item_bytes > self._max_memory:
            return
        with self._lock:
            if key in self._cache:
                self._current_memory -= self._cache[key].nbytes
                del self._cache[key]
            while self._current_memory + item_bytes > self._max_memory and self._cache:
                _, evicted = self._cache.popitem(last=False)
                self._current_memory -= evicted.nbytes
            self._cache[key] = value
            self._current_memory += item_bytes

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._current_memory = 0

    @property
    def current_memory(self) -> int:
        return self._current_memory

    def __len__(self) -> int:
        return len(self._cache)
