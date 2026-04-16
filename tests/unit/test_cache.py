"""Tests for memory-bounded LRU cache."""

import threading

import numpy as np

from squid_tools.core.cache import MemoryBoundedLRUCache


class TestMemoryBoundedLRUCache:
    def test_get_set(self) -> None:
        cache: MemoryBoundedLRUCache = MemoryBoundedLRUCache(max_bytes=1024 * 1024)
        arr = np.zeros((10, 10), dtype=np.uint16)
        cache.put("key1", arr)
        result = cache.get("key1")
        assert result is not None
        assert np.array_equal(result, arr)

    def test_miss_returns_none(self) -> None:
        cache: MemoryBoundedLRUCache = MemoryBoundedLRUCache(max_bytes=1024 * 1024)
        assert cache.get("missing") is None

    def test_evicts_lru_when_full(self) -> None:
        # Cache fits ~2 arrays of 100 bytes each
        cache: MemoryBoundedLRUCache = MemoryBoundedLRUCache(max_bytes=250)
        a1 = np.zeros(100, dtype=np.uint8)  # 100 bytes
        a2 = np.zeros(100, dtype=np.uint8)  # 100 bytes
        a3 = np.zeros(100, dtype=np.uint8)  # 100 bytes

        cache.put("a1", a1)
        cache.put("a2", a2)
        cache.put("a3", a3)  # should evict a1

        assert cache.get("a1") is None
        assert cache.get("a2") is not None
        assert cache.get("a3") is not None

    def test_rejects_oversized_item(self) -> None:
        cache: MemoryBoundedLRUCache = MemoryBoundedLRUCache(max_bytes=50)
        big = np.zeros(100, dtype=np.uint8)  # 100 bytes > 50
        cache.put("big", big)
        assert cache.get("big") is None

    def test_access_updates_recency(self) -> None:
        cache: MemoryBoundedLRUCache = MemoryBoundedLRUCache(max_bytes=250)
        a1 = np.zeros(100, dtype=np.uint8)
        a2 = np.zeros(100, dtype=np.uint8)
        a3 = np.zeros(100, dtype=np.uint8)

        cache.put("a1", a1)
        cache.put("a2", a2)
        cache.get("a1")  # touch a1, making a2 the LRU
        cache.put("a3", a3)  # should evict a2, not a1

        assert cache.get("a1") is not None
        assert cache.get("a2") is None
        assert cache.get("a3") is not None

    def test_current_bytes(self) -> None:
        cache: MemoryBoundedLRUCache = MemoryBoundedLRUCache(max_bytes=1024)
        arr = np.zeros(100, dtype=np.uint8)
        cache.put("k", arr)
        assert cache.current_bytes == 100

    def test_thread_safety(self) -> None:
        """Basic thread safety: concurrent puts don't crash."""
        cache: MemoryBoundedLRUCache = MemoryBoundedLRUCache(max_bytes=10000)

        def writer(prefix: str) -> None:
            for i in range(50):
                cache.put(f"{prefix}_{i}", np.zeros(10, dtype=np.uint8))

        threads = [threading.Thread(target=writer, args=(f"t{i}",)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should not crash; cache should have some entries
        assert cache.current_bytes > 0
