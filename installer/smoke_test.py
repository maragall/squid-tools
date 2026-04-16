"""Post-freeze smoke tests for the bundled squid-tools application.

Run via: squid-tools.exe --smoke-test
Tests verify all critical imports and basic functionality work in the bundle.
"""

import os
import sys
import tempfile

import numpy


def _test(name, fn):
    """Run a single test, print PASS/FAIL, return success bool."""
    try:
        fn()
        print(f"PASS: {name}")
        return True
    except Exception as e:
        print(f"FAIL: {name} -- {e}")
        return False


def run():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    results = []

    def t_import_squid_tools():
        import squid_tools
        assert squid_tools.__version__

    def t_data_model():
        from squid_tools.core.data_model import AcquisitionFormat
        assert AcquisitionFormat.OME_TIFF == "OME_TIFF"

    def t_readers():
        from squid_tools.core.readers import detect_reader  # noqa: F401

    def t_plugins():
        from squid_tools.processing.base import ProcessingPlugin  # noqa: F401

    def t_pipeline():
        from squid_tools.core.pipeline import Pipeline
        p = Pipeline()
        assert len(p) == 0

    def t_cache():
        from squid_tools.core.cache import MemoryBoundedLRUCache
        c = MemoryBoundedLRUCache(max_bytes=1024)
        c.put("test", numpy.zeros(10, dtype=numpy.uint8))
        assert c.get("test") is not None

    def t_gpu_detection():
        from squid_tools.core.gpu import detect_gpu
        info = detect_gpu()
        assert isinstance(info.available, bool)

    def t_dask_array():
        import dask.array
        assert dask.array.zeros((10, 10)).compute().shape == (10, 10)

    def t_tifffile():
        import tifffile
        arr = numpy.zeros((10, 10), dtype=numpy.uint16)
        with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as f:
            path = f.name
        try:
            tifffile.imwrite(path, arr)
            data = tifffile.imread(path)
            assert data.shape == (10, 10)
        finally:
            os.unlink(path)

    def t_pydantic():
        from pydantic import BaseModel

        class TestModel(BaseModel):
            x: int = 1

        m = TestModel(x=5)
        assert m.x == 5

    def t_pyside6():
        from PySide6.QtWidgets import QApplication  # noqa: F401

    def t_vispy():
        import vispy  # noqa: F401

    def t_viewer_canvas():
        from squid_tools.viewer.canvas import VispyCanvas

        c = VispyCanvas()
        c.set_image(numpy.zeros((10, 10), dtype=numpy.float32))
        assert c.has_image()

    def t_gui_main_window():
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
        from squid_tools.gui.app import MainWindow
        w = MainWindow()
        assert w.windowTitle() == "Squid-Tools"

    def t_stitcher_plugin():
        from squid_tools.processing.stitching.plugin import StitcherPlugin
        p = StitcherPlugin()
        assert p.name == "Stitcher"
        assert p.category == "stitching"

    def t_flatfield_correction():
        from squid_tools.processing.flatfield.correction import apply_flatfield
        flat = numpy.ones((10, 10), dtype=numpy.float32)
        frame = numpy.full((10, 10), 500.0, dtype=numpy.float32)
        result = apply_flatfield(frame, flat)
        assert result.shape == (10, 10)

    def t_dev_mode_loader():
        from pathlib import Path

        from squid_tools.gui.dev_panel import load_plugin_from_file
        # Load a non-existent file should return empty
        result = load_plugin_from_file(Path("/nonexistent.py"))
        assert result == []

    tests = [
        ("import squid_tools", t_import_squid_tools),
        ("data model", t_data_model),
        ("readers", t_readers),
        ("plugins", t_plugins),
        ("pipeline", t_pipeline),
        ("cache", t_cache),
        ("GPU detection", t_gpu_detection),
        ("dask.array", t_dask_array),
        ("tifffile read/write", t_tifffile),
        ("pydantic", t_pydantic),
        ("PySide6", t_pyside6),
        ("vispy", t_vispy),
        ("viewer canvas", t_viewer_canvas),
        ("GUI MainWindow", t_gui_main_window),
        ("stitcher plugin", t_stitcher_plugin),
        ("flatfield correction", t_flatfield_correction),
        ("dev mode loader", t_dev_mode_loader),
    ]

    for name, fn in tests:
        results.append(_test(name, fn))

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} smoke tests passed.")
    sys.exit(0 if all(results) else 1)
