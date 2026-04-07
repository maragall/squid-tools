import numpy as np

from squid_tools.core.cache import MemoryBoundedLRUCache


def test_cache_stores_and_retrieves():
    cache = MemoryBoundedLRUCache(max_memory_bytes=1024 * 1024)
    arr = np.zeros((10, 10), dtype=np.uint16)
    cache.put("key1", arr)
    result = cache.get("key1")
    assert result is not None
    np.testing.assert_array_equal(result, arr)


def test_cache_returns_none_for_missing_key():
    cache = MemoryBoundedLRUCache(max_memory_bytes=1024 * 1024)
    assert cache.get("nonexistent") is None


def test_cache_evicts_lru_when_full():
    max_bytes = 1000
    cache = MemoryBoundedLRUCache(max_memory_bytes=max_bytes)
    for i in range(6):
        cache.put(f"key{i}", np.zeros(100, dtype=np.uint16))
    assert cache.get("key0") is None
    assert cache.get("key5") is not None


def test_cache_rejects_oversized_item():
    cache = MemoryBoundedLRUCache(max_memory_bytes=100)
    big = np.zeros(1000, dtype=np.uint16)
    cache.put("big", big)
    assert cache.get("big") is None


def test_cache_move_to_end_on_hit():
    cache = MemoryBoundedLRUCache(max_memory_bytes=800)
    for i in range(3):
        cache.put(f"key{i}", np.zeros(100, dtype=np.uint16))
    cache.get("key0")
    cache.put("key3", np.zeros(100, dtype=np.uint16))
    cache.put("key4", np.zeros(100, dtype=np.uint16))
    assert cache.get("key1") is None
    assert cache.get("key0") is not None


def test_cache_thread_safety():
    import threading
    cache = MemoryBoundedLRUCache(max_memory_bytes=1024 * 1024)
    errors = []

    def writer(start: int):
        try:
            for i in range(100):
                cache.put(f"w{start}_{i}", np.zeros(10, dtype=np.uint16))
        except Exception as e:
            errors.append(e)

    def reader(start: int):
        try:
            for i in range(100):
                cache.get(f"w{start}_{i}")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(j,)) for j in range(4)]
    threads += [threading.Thread(target=reader, args=(j,)) for j in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 0
