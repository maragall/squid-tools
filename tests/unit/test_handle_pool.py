"""Tests for TiffFile handle pool."""

from pathlib import Path

import numpy as np
import tifffile

from squid_tools.core.handle_pool import TiffFileHandlePool


def _create_test_tiff(path: Path) -> Path:
    """Create a minimal TIFF file for testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.zeros((64, 64), dtype=np.uint16)
    tifffile.imwrite(str(path), data)
    return path


class TestTiffFileHandlePool:
    def test_open_and_read(self, tmp_path: Path) -> None:
        pool = TiffFileHandlePool(max_handles=4)
        tiff_path = _create_test_tiff(tmp_path / "test.tiff")
        handle, lock = pool.get(tiff_path)
        with lock:
            data = handle.asarray()
        assert data.shape == (64, 64)

    def test_reuses_handle(self, tmp_path: Path) -> None:
        pool = TiffFileHandlePool(max_handles=4)
        tiff_path = _create_test_tiff(tmp_path / "test.tiff")
        h1, _ = pool.get(tiff_path)
        h2, _ = pool.get(tiff_path)
        assert h1 is h2

    def test_evicts_lru_handle(self, tmp_path: Path) -> None:
        pool = TiffFileHandlePool(max_handles=2)
        p1 = _create_test_tiff(tmp_path / "a.tiff")
        p2 = _create_test_tiff(tmp_path / "b.tiff")
        p3 = _create_test_tiff(tmp_path / "c.tiff")

        pool.get(p1)
        pool.get(p2)
        pool.get(p3)  # should evict p1

        assert pool.handle_count == 2

    def test_close_all(self, tmp_path: Path) -> None:
        pool = TiffFileHandlePool(max_handles=4)
        p1 = _create_test_tiff(tmp_path / "a.tiff")
        pool.get(p1)
        pool.close_all()
        assert pool.handle_count == 0
