from pathlib import Path

import numpy as np
import tifffile

from squid_tools.core.handle_pool import TiffHandlePool


def _write_test_tiff(path: Path, data: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(str(path), data)


def test_pool_reads_file(tmp_path: Path):
    img = np.random.randint(0, 4096, (256, 256), dtype=np.uint16)
    fpath = tmp_path / "test.tiff"
    _write_test_tiff(fpath, img)
    pool = TiffHandlePool(max_handles=16)
    result = pool.read(fpath, page_index=0)
    np.testing.assert_array_equal(result, img)
    pool.close_all()


def test_pool_caches_handles(tmp_path: Path):
    img = np.zeros((64, 64), dtype=np.uint16)
    fpath = tmp_path / "test.tiff"
    _write_test_tiff(fpath, img)
    pool = TiffHandlePool(max_handles=16)
    pool.read(fpath, page_index=0)
    pool.read(fpath, page_index=0)
    assert pool.open_count == 1
    pool.close_all()


def test_pool_evicts_when_full(tmp_path: Path):
    pool = TiffHandlePool(max_handles=3)
    for i in range(5):
        fpath = tmp_path / f"test_{i}.tiff"
        _write_test_tiff(fpath, np.zeros((16, 16), dtype=np.uint16))
        pool.read(fpath, page_index=0)
    assert pool.open_count <= 3
    pool.close_all()


def test_pool_concurrent_reads(tmp_path: Path):
    import threading
    paths = []
    for i in range(10):
        fpath = tmp_path / f"test_{i}.tiff"
        _write_test_tiff(fpath, np.random.randint(0, 100, (32, 32), dtype=np.uint16))
        paths.append(fpath)
    pool = TiffHandlePool(max_handles=128)
    errors = []
    def reader(fpath: Path):
        try:
            for _ in range(20):
                pool.read(fpath, page_index=0)
        except Exception as e:
            errors.append(e)
    threads = [threading.Thread(target=reader, args=(p,)) for p in paths]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 0
    pool.close_all()
