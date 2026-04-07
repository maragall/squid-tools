"""TiffFile handle pool with LRU eviction and per-file locking.

Pattern from ndviewer_light: 128-handle cap, per-file locks for
parallel reads across files while serializing same-file reads.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

import numpy as np
import tifffile


class TiffHandlePool:
    """Pool of open TiffFile handles with LRU eviction."""

    def __init__(self, max_handles: int = 128) -> None:
        self._max_handles = max_handles
        self._handles: OrderedDict[Path, tuple[tifffile.TiffFile, threading.Lock]] = OrderedDict()
        self._global_lock = threading.Lock()

    def read(self, path: Path, page_index: int = 0) -> np.ndarray:
        path = path.resolve()
        file_lock = self._get_or_create_handle(path)
        with file_lock:
            tf, _ = self._handles[path]
            return tf.pages[page_index].asarray()

    def _get_or_create_handle(self, path: Path) -> threading.Lock:
        with self._global_lock:
            if path in self._handles:
                self._handles.move_to_end(path)
                return self._handles[path][1]
            to_close = []
            while len(self._handles) >= self._max_handles:
                _, (old_tf, _) = self._handles.popitem(last=False)
                to_close.append(old_tf)
        for tf in to_close:
            tf.close()
        tf = tifffile.TiffFile(str(path))
        lock = threading.Lock()
        with self._global_lock:
            self._handles[path] = (tf, lock)
        return lock

    @property
    def open_count(self) -> int:
        return len(self._handles)

    def close_all(self) -> None:
        with self._global_lock:
            for tf, _ in self._handles.values():
                tf.close()
            self._handles.clear()
