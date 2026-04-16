# Squid-Tools Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the distribution infrastructure: frozen .exe entry point, PyInstaller spec, smoke tests, GPU runtime detection, and a CLI entry point.

**Architecture:** A frozen entry point (`installer/entry.py`) sets up Qt plugin paths and crash logging for PyInstaller builds. A PyInstaller spec bundles all dependencies. A smoke test suite verifies the bundle works. GPU detection happens at runtime via `try: import cupy`. A `__main__.py` provides `python -m squid_tools` CLI entry.

**Tech Stack:** PyInstaller, PyQt5, napari, the existing squid_tools package

**Spec:** `docs/superpowers/specs/2026-04-07-squid-tools-design.md` (Distribution section)

**Reference:** `_audit/ndviewer_light/installer/` (proven patterns)

---

## File Structure

```
squid_tools/
├── __main__.py                  # python -m squid_tools entry point
installer/
├── entry.py                     # Frozen exe entry point (crash logging, Qt paths)
├── smoke_test.py                # Post-freeze smoke tests
├── squid_tools.spec             # PyInstaller spec file
tests/
├── unit/
│   ├── test_gpu_detection.py    # GPU runtime detection tests
│   └── test_entry.py            # Entry point tests
```

---

### Task 1: CLI Entry Point

**Files:**
- Create: `squid_tools/__main__.py`
- Create: `tests/unit/test_entry.py`

- [ ] **Step 1: Write failing test**

`tests/unit/test_entry.py`:
```python
"""Tests for CLI entry point."""

import subprocess
import sys


class TestCLIEntry:
    def test_module_entry_help(self) -> None:
        """python -m squid_tools --help should exit 0."""
        result = subprocess.run(
            [sys.executable, "-m", "squid_tools", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            env={"QT_QPA_PLATFORM": "offscreen", "PATH": ""},
        )
        assert result.returncode == 0
        assert "squid-tools" in result.stdout.lower() or "usage" in result.stdout.lower()

    def test_module_entry_version(self) -> None:
        """python -m squid_tools --version should print version."""
        result = subprocess.run(
            [sys.executable, "-m", "squid_tools", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            env={"QT_QPA_PLATFORM": "offscreen", "PATH": ""},
        )
        assert result.returncode == 0
        assert "0.1.0" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_entry.py -v`
Expected: FAIL

- [ ] **Step 3: Implement __main__.py**

`squid_tools/__main__.py`:
```python
"""CLI entry point: python -m squid_tools."""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="squid-tools",
        description="Squid-Tools: Post-processing connector for Cephla-Lab/Squid",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"squid-tools {_get_version()}",
    )
    parser.add_argument(
        "--dev",
        nargs="?",
        const=True,
        default=None,
        metavar="PLUGIN_FILE",
        help="Launch in dev mode, optionally hot-loading a plugin file",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to a Squid acquisition directory to open",
    )

    args = parser.parse_args()

    # Import GUI only when actually launching (keeps --help fast)
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", ""))

    from PyQt5.QtWidgets import QApplication
    from squid_tools.gui.app import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


def _get_version() -> str:
    from squid_tools import __version__
    return __version__


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_entry.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add squid_tools/__main__.py tests/unit/test_entry.py
git commit -m "feat: CLI entry point (python -m squid_tools)"
```

---

### Task 2: GPU Runtime Detection

**Files:**
- Create: `squid_tools/core/gpu.py`
- Create: `tests/unit/test_gpu_detection.py`

- [ ] **Step 1: Write failing test**

`tests/unit/test_gpu_detection.py`:
```python
"""Tests for GPU runtime detection."""

from squid_tools.core.gpu import detect_gpu, GPUInfo


class TestGPUDetection:
    def test_returns_gpu_info(self) -> None:
        info = detect_gpu()
        assert isinstance(info, GPUInfo)

    def test_has_available_field(self) -> None:
        info = detect_gpu()
        assert isinstance(info.available, bool)

    def test_has_name_field(self) -> None:
        info = detect_gpu()
        assert isinstance(info.name, str)

    def test_has_backend_field(self) -> None:
        info = detect_gpu()
        assert info.backend in ("cupy", "none")

    def test_cpu_fallback_message(self) -> None:
        info = detect_gpu()
        if not info.available:
            assert "CPU" in info.name or "cpu" in info.name.lower() or info.name == "CPU only"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_gpu_detection.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement GPU detection**

`squid_tools/core/gpu.py`:
```python
"""GPU runtime detection.

Detects CUDA GPU via CuPy at runtime. Falls back to CPU silently.
No build-time CUDA dependency required.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GPUInfo:
    """GPU detection result."""

    available: bool
    name: str
    backend: str  # "cupy" or "none"
    device_id: int = 0


def detect_gpu() -> GPUInfo:
    """Detect GPU at runtime. Returns GPUInfo with CPU fallback.

    Tries CuPy first. If not installed or no CUDA device, returns
    CPU-only info. Never raises.
    """
    try:
        import cupy
        device = cupy.cuda.Device(0)
        props = cupy.cuda.runtime.getDeviceProperties(0)
        name = props["name"].decode() if isinstance(props["name"], bytes) else str(props["name"])
        return GPUInfo(available=True, name=name, backend="cupy", device_id=0)
    except Exception:
        pass

    return GPUInfo(available=False, name="CPU only", backend="none")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_gpu_detection.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add squid_tools/core/gpu.py tests/unit/test_gpu_detection.py
git commit -m "feat: GPU runtime detection with CuPy/CPU fallback"
```

---

### Task 3: Frozen Entry Point

**Files:**
- Create: `installer/entry.py`

- [ ] **Step 1: Create frozen entry point**

`installer/entry.py`:
```python
"""Frozen entry point for PyInstaller-built squid-tools.

Sets up Qt plugin paths, environment variables, and crash logging
for the bundled application. Based on ndviewer_light's proven pattern.
"""

import os
import sys
import traceback

_log_path = ""

if getattr(sys, "frozen", False):
    # Running as PyInstaller bundle
    os.environ["QT_PLUGIN_PATH"] = os.path.join(
        sys._MEIPASS, "PyQt5", "Qt5", "plugins"  # type: ignore[attr-defined]
    )
    _log_path = os.path.join(os.path.dirname(sys.executable), "crash.log")

if "--smoke-test" in sys.argv:
    from installer.smoke_test import run

    run()
else:
    try:
        from squid_tools.__main__ import main

        main()
    except Exception:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        if getattr(sys, "frozen", False) and _log_path:
            with open(_log_path, "w") as f:
                f.write(tb)
            print(f"\nCrash log written to: {_log_path}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('installer/entry.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add installer/entry.py
git commit -m "feat: frozen entry point for PyInstaller builds"
```

---

### Task 4: Smoke Test Suite

**Files:**
- Create: `installer/smoke_test.py`

- [ ] **Step 1: Create smoke test**

`installer/smoke_test.py`:
```python
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
        from squid_tools.core.data_model import Acquisition, AcquisitionFormat
        assert AcquisitionFormat.OME_TIFF == "OME_TIFF"

    def t_readers():
        from squid_tools.core.readers import detect_reader  # noqa: F401

    def t_plugins():
        from squid_tools.plugins.base import ProcessingPlugin  # noqa: F401

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

    def t_pyqt5():
        from PyQt5.QtWidgets import QApplication  # noqa: F401

    def t_napari():
        import napari  # noqa: F401

    def t_gui_main_window():
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
        from squid_tools.gui.app import MainWindow
        w = MainWindow()
        assert w.windowTitle() == "Squid-Tools"

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
        ("PyQt5", t_pyqt5),
        ("napari", t_napari),
        ("GUI MainWindow", t_gui_main_window),
    ]

    for name, fn in tests:
        results.append(_test(name, fn))

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} smoke tests passed.")
    sys.exit(0 if all(results) else 1)
```

- [ ] **Step 2: Run smoke tests directly (not frozen)**

Run: `QT_QPA_PLATFORM=offscreen python -c "from installer.smoke_test import run; run()"`
Expected: All PASS (13/13)

- [ ] **Step 3: Commit**

```bash
git add installer/smoke_test.py
git commit -m "feat: post-freeze smoke test suite (13 tests)"
```

---

### Task 5: PyInstaller Spec

**Files:**
- Create: `installer/squid_tools.spec`

- [ ] **Step 1: Create PyInstaller spec**

`installer/squid_tools.spec`:
```python
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for squid-tools.

Run from the installer/ directory:
  cd installer && python -m PyInstaller squid_tools.spec --noconfirm

Based on ndviewer_light's proven bundling pattern.
"""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect data files
napari_datas = collect_data_files("napari")
vispy_datas = collect_data_files("vispy")
pydantic_datas = collect_data_files("pydantic")

# Collect all submodules to ensure complete bundling
squid_tools_imports = collect_submodules("squid_tools")
napari_imports = collect_submodules("napari")
vispy_imports = collect_submodules("vispy")

a = Analysis(
    ["entry.py"],
    pathex=[os.path.abspath("..")],
    binaries=[],
    datas=napari_datas + vispy_datas + pydantic_datas,
    hiddenimports=squid_tools_imports
    + napari_imports
    + vispy_imports
    + [
        "PyQt5",
        "PyQt5.QtCore",
        "PyQt5.QtGui",
        "PyQt5.QtWidgets",
        "superqt",
        "dask",
        "dask.array",
        "tifffile",
        "pydantic",
        "pydantic.deprecated",
        "yaml",
        "zarr",
        "numpy",
        "numpy.core._methods",
        "numpy.lib.format",
        "xml.etree.ElementTree",
        "importlib.metadata",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="squid-tools",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="squid-tools",
)
```

- [ ] **Step 2: Verify spec parses**

Run: `python -c "import ast; ast.parse(open('installer/squid_tools.spec').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add installer/squid_tools.spec
git commit -m "feat: PyInstaller spec for Windows .exe and Linux bundling"
```

---

### Task 6: Wire GPU Detection into Log Panel

**Files:**
- Modify: `squid_tools/gui/log_panel.py`
- Modify: `tests/unit/test_gui_log_panel.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_gui_log_panel.py`:
```python
class TestLogPanelGPUIntegration:
    def test_auto_detects_gpu_on_init(self, qtbot: QtBot) -> None:
        panel = LogPanel()
        qtbot.addWidget(panel)
        gpu_text = panel.gpu_text()
        # Should contain either a GPU name or "CPU only"
        assert "GPU:" in gpu_text
        assert len(gpu_text) > 5  # "GPU: " + something
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_gui_log_panel.py::TestLogPanelGPUIntegration -v`

If it already passes (log_panel.py already calls `_detect_gpu`), skip to Step 4.

- [ ] **Step 3: Update log_panel.py to use core gpu module**

Replace the `_detect_gpu` method in `squid_tools/gui/log_panel.py`:
```python
    def _detect_gpu(self) -> None:
        """Detect GPU at startup using core detection."""
        from squid_tools.core.gpu import detect_gpu

        info = detect_gpu()
        if info.available:
            self.set_gpu_info(info.name)
        else:
            self.set_gpu_info("CPU only")
```

- [ ] **Step 4: Run all tests**

Run: `QT_QPA_PLATFORM=offscreen pytest -v --tb=short`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add squid_tools/gui/log_panel.py tests/unit/test_gui_log_panel.py
git commit -m "feat: wire GPU runtime detection into log panel"
```

---

### Task 7: Final Distribution Verification

- [ ] **Step 1: Run full test suite**

Run: `QT_QPA_PLATFORM=offscreen pytest -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Run ruff**

Run: `ruff check squid_tools/ tests/ installer/`
Expected: Clean

- [ ] **Step 3: Run smoke tests**

Run: `QT_QPA_PLATFORM=offscreen python -c "from installer.smoke_test import run; run()"`
Expected: 13/13 pass

- [ ] **Step 4: Verify CLI**

Run: `QT_QPA_PLATFORM=offscreen python -m squid_tools --version`
Expected: `squid-tools 0.1.0`

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "chore: final distribution verification"
```
