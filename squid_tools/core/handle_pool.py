"""TiffFile handle pool with LRU eviction.

Keeps up to max_handles open TiffFile objects to avoid
re-parsing IFD chains on repeated reads. Per-file locks
enable parallel reads across files while serializing
same-file reads.

Pattern from ndviewer_light, proven in production.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

import tifffile


class TiffFileHandlePool:
    """Pool of open TiffFile handles with LRU eviction."""

    def __init__(self, max_handles: int = 128) -> None:
        self._max_handles = max_handles
        self._handles: OrderedDict[Path, tuple[tifffile.TiffFile, threading.Lock]] = OrderedDict()
        self._global_lock = threading.Lock()

    @property
    def handle_count(self) -> int:
        return len(self._handles)

    def get(self, path: Path) -> tuple[tifffile.TiffFile, threading.Lock]:
        """Get or open a TiffFile handle for the given path.

        Returns (TiffFile, per-file Lock). Caller must acquire the
        per-file lock before reading from the handle.
        """
        resolved = path.resolve()
        with self._global_lock:
            if resolved in self._handles:
                self._handles.move_to_end(resolved)
                return self._handles[resolved]

            # Evict LRU handles if at capacity
            to_close: list[tifffile.TiffFile] = []
            while len(self._handles) >= self._max_handles:
                _, (evicted_handle, _) = self._handles.popitem(last=False)
                to_close.append(evicted_handle)

        # Close evicted handles outside the global lock
        for h in to_close:
            h.close()

        handle = tifffile.TiffFile(str(resolved))
        lock = threading.Lock()

        with self._global_lock:
            self._handles[resolved] = (handle, lock)

        return handle, lock

    def close_all(self) -> None:
        """Close all open handles."""
        with self._global_lock:
            for handle, _ in self._handles.values():
                handle.close()
            self._handles.clear()
