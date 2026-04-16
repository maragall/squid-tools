# Namespace Restructure + PySide6 Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize squid-tools into namespace packages (core, viewer, processing, app) and migrate from PyQt5+napari to PySide6+vispy. All 123 existing tests must pass after restructure.

**Architecture:** The monorepo splits into independently installable packages sharing the `squid_tools` namespace. PyQt5 imports become PySide6 imports. napari-based viewer/mosaic are replaced with placeholder vispy widgets (Sub-plan B builds the real viewer). The processing/ directory replaces plugins/.

**Tech Stack:** PySide6 (Qt 6, LGPL), vispy, hatchling, existing core library

**Spec:** `docs/superpowers/specs/2026-04-09-squid-tools-v1-design.md`

---

## Overview of Changes

**What moves:**
- `squid_tools/core/` stays (becomes its own package with pyproject.toml)
- `squid_tools/gui/` stays (becomes part of the app package)
- `squid_tools/plugins/base.py` moves to `squid_tools/processing/base.py`
- `squid_tools/plugins/background.py` deleted (deferred to future cycle)
- `squid_tools/plugins/flatfield.py` moves to `squid_tools/processing/flatfield/plugin.py`

**What's replaced:**
- `squid_tools/gui/viewer.py` (napari) replaced with vispy placeholder
- `squid_tools/gui/mosaic.py` (napari) replaced with vispy placeholder
- All `from PyQt5` imports become `from PySide6`
- All `pyqtSignal` become `Signal` (PySide6 naming)
- napari dependency removed entirely

**What's added:**
- Per-package `pyproject.toml` files
- `squid_tools/processing/` package structure
- `squid_tools/viewer/` package structure (placeholder)

---

### Task 1: PySide6 Migration (imports only)

**Files:**
- Modify: `pyproject.toml`
- Modify: all files under `squid_tools/gui/`
- Modify: `squid_tools/__main__.py`
- Modify: `installer/smoke_test.py`
- Modify: all GUI test files

This task only changes imports. No restructuring yet.

- [ ] **Step 1: Update pyproject.toml dependencies**

Replace PyQt5 and napari with PySide6 and vispy:

```toml
dependencies = [
    "pydantic>=2.10",
    "numpy>=1.24",
    "dask[array]>=2024.1",
    "tifffile>=2024.1",
    "pyyaml>=6.0",
    "zarr>=2.16",
    "PySide6>=6.6",
    "vispy>=0.14",
    "scipy>=1.10",
]

[project.optional-dependencies]
gpu = ["cupy-cuda12x>=13.0"]
dev = [
    "pytest>=8.0",
    "pytest-qt>=4.2",
    "ruff>=0.4",
    "mypy>=1.10",
]
```

Remove the `gui` optional dependency group (PySide6 is now in base deps). Remove `napari`, `superqt`, `sep` from base deps.

- [ ] **Step 2: Install new deps**

Run: `pip install -e ".[dev]"`

- [ ] **Step 3: Migrate all PyQt5 imports to PySide6**

The mapping:
```
from PyQt5.QtWidgets import ...  ->  from PySide6.QtWidgets import ...
from PyQt5.QtCore import ...     ->  from PySide6.QtCore import ...
from PyQt5.QtCore import pyqtSignal  ->  from PySide6.QtCore import Signal
pyqtSignal  ->  Signal  (in class bodies)
```

Files to change:
- `squid_tools/gui/log_panel.py`: `from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget`
- `squid_tools/gui/controls.py`: `from PySide6.QtCore import Signal` and `from PySide6.QtWidgets import ...`. Replace `pyqtSignal` with `Signal` in class body.
- `squid_tools/gui/region_selector.py`: same pattern
- `squid_tools/gui/processing_tabs.py`: same pattern
- `squid_tools/gui/app.py`: `from PySide6.QtCore import Qt` and `from PySide6.QtWidgets import ...`
- `squid_tools/gui/embed.py`: `from PySide6.QtWidgets import ...`
- `squid_tools/gui/viewer.py`: `from PySide6.QtWidgets import ...`. Remove napari import entirely. Replace with a placeholder QLabel.
- `squid_tools/gui/mosaic.py`: same as viewer.py
- `squid_tools/__main__.py`: `from PySide6.QtWidgets import QApplication`
- `installer/smoke_test.py`: `from PySide6.QtWidgets import QApplication`. Remove napari test.

- [ ] **Step 4: Replace napari viewer with placeholder**

`squid_tools/gui/viewer.py`:
```python
"""Single FOV viewer placeholder. Will be replaced by vispy viewer in Sub-plan B."""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class SingleFOVViewer(QWidget):
    """Placeholder for the vispy-based single FOV viewer."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel("Viewer: no data loaded")
        self._label.setStyleSheet("color: #aaaaaa; background: #2a2a2a;")
        layout.addWidget(self._label)
        self._current_frame: np.ndarray | None = None

    def display_frame(self, frame: np.ndarray, name: str = "image") -> None:
        self._current_frame = frame
        h, w = frame.shape[:2]
        self._label.setText(f"FOV: {name} ({w}x{h})")

    def display_processed(self, frame: np.ndarray, name: str = "processed") -> None:
        h, w = frame.shape[:2]
        self._label.setText(f"Processed: {name} ({w}x{h})")

    def clear_layers(self) -> None:
        self._current_frame = None
        self._label.setText("Viewer: no data loaded")

    @property
    def napari_viewer(self) -> None:
        return None
```

`squid_tools/gui/mosaic.py`:
```python
"""Mosaic view placeholder. Will be replaced by vispy viewer in Sub-plan B."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from squid_tools.core.data_model import Region


class MosaicView(QWidget):
    """Placeholder for the vispy-based mosaic viewer."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel("Mosaic: no data loaded")
        self._label.setStyleSheet("color: #aaaaaa; background: #2a2a2a;")
        layout.addWidget(self._label)

    def load_region(
        self,
        region: Region,
        frames: dict[int, np.ndarray],
        pixel_size_um: float,
    ) -> None:
        n_fovs = len(frames)
        self._label.setText(f"Mosaic: {region.region_id} ({n_fovs} FOVs)")

    def set_borders_visible(self, visible: bool) -> None:
        pass

    def display_processed(
        self, fov_index: int, frame: np.ndarray, y_px: float, x_px: float
    ) -> None:
        pass

    def clear(self) -> None:
        self._label.setText("Mosaic: no data loaded")

    @property
    def napari_viewer(self) -> None:
        return None
```

- [ ] **Step 5: Update smoke test**

In `installer/smoke_test.py`, replace the PyQt5 and napari tests:
```python
    def t_pyside6():
        from PySide6.QtWidgets import QApplication  # noqa: F401

    def t_vispy():
        import vispy  # noqa: F401
```

Remove `t_napari` test. Update the test list accordingly.

- [ ] **Step 6: Update test files for PySide6**

In all test files under `tests/unit/test_gui_*.py` and `tests/integration/`:
- Replace `from pytestqt.qtbot import QtBot` (should still work with PySide6 if pytest-qt is configured)
- Add to `conftest.py` or `pyproject.toml`:
```toml
[tool.pytest.ini_options]
qt_api = "pyside6"
```

- [ ] **Step 7: Run full test suite**

Run: `QT_QPA_PLATFORM=offscreen pytest -v --tb=short`
Expected: All 123 tests PASS (minus any napari-specific tests that were removed)

- [ ] **Step 8: Run ruff**

Run: `ruff check squid_tools/ tests/ installer/`
Expected: Clean

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: migrate from PyQt5+napari to PySide6+vispy"
```

---

### Task 2: Move plugins/ to processing/

**Files:**
- Create: `squid_tools/processing/__init__.py`
- Create: `squid_tools/processing/base.py` (moved from plugins/base.py)
- Create: `squid_tools/processing/flatfield/` (moved from plugins/flatfield.py)
- Delete: `squid_tools/plugins/` directory
- Delete: `squid_tools/plugins/background.py` (deferred to future cycle)
- Modify: all files importing from `squid_tools.plugins`

- [ ] **Step 1: Create processing package**

```
squid_tools/processing/__init__.py
squid_tools/processing/base.py          # copy of plugins/base.py
squid_tools/processing/flatfield/__init__.py
squid_tools/processing/flatfield/plugin.py    # moved from plugins/flatfield.py
squid_tools/processing/flatfield/correction.py  # the actual algorithm (extract from plugin.py)
```

`squid_tools/processing/__init__.py`:
```python
"""Processing modules. Each subdirectory is an independently installable package."""
```

`squid_tools/processing/base.py`: Copy `squid_tools/plugins/base.py` exactly, no changes.

`squid_tools/processing/flatfield/__init__.py`:
```python
"""Flatfield correction processing module."""

from squid_tools.processing.flatfield.plugin import FlatfieldPlugin

__all__ = ["FlatfieldPlugin"]
```

`squid_tools/processing/flatfield/plugin.py`: Copy `squid_tools/plugins/flatfield.py` and update imports:
```python
from squid_tools.processing.base import ProcessingPlugin
```

- [ ] **Step 2: Update all imports**

Search and replace across the codebase:
```
from squid_tools.plugins.base import ProcessingPlugin
  -> from squid_tools.processing.base import ProcessingPlugin

from squid_tools.plugins.background import BackgroundPlugin
  -> DELETE (deferred)

from squid_tools.plugins.flatfield import FlatfieldPlugin, FlatfieldParams
  -> from squid_tools.processing.flatfield.plugin import FlatfieldPlugin, FlatfieldParams
```

Files that import from plugins:
- `squid_tools/gui/app.py` (registers plugins)
- `squid_tools/core/pipeline.py` (uses ProcessingPlugin)
- `tests/unit/test_registry.py` (uses ProcessingPlugin)
- `tests/unit/test_pipeline.py` (uses ProcessingPlugin)
- `tests/unit/test_controller.py` (uses ProcessingPlugin)
- `tests/unit/test_plugin_flatfield.py`
- `tests/unit/test_gui_processing_tabs.py`
- `tests/integration/test_gui_smoke.py`
- `tests/integration/test_end_to_end.py`

- [ ] **Step 3: Update MainWindow plugin registration**

In `squid_tools/gui/app.py`, update `_register_default_plugins`:
```python
    def _register_default_plugins(self) -> None:
        try:
            from squid_tools.processing.flatfield.plugin import FlatfieldPlugin
            self.controller.registry.register(FlatfieldPlugin())
        except ImportError:
            pass
```

Remove the BackgroundPlugin registration entirely.

- [ ] **Step 4: Delete old plugins directory**

```bash
rm -rf squid_tools/plugins/
```

- [ ] **Step 5: Delete background plugin test**

```bash
rm tests/unit/test_plugin_background.py
```

Update any test that references BackgroundPlugin to use FlatfieldPlugin instead or remove the reference.

- [ ] **Step 6: Run full test suite**

Run: `QT_QPA_PLATFORM=offscreen pytest -v --tb=short`
Expected: All tests PASS (count may decrease by a few due to removed background tests)

- [ ] **Step 7: Run ruff**

Run: `ruff check squid_tools/ tests/`
Expected: Clean

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: move plugins/ to processing/, drop background (future cycle)"
```

---

### Task 3: Add process_region() to Plugin ABC

**Files:**
- Modify: `squid_tools/processing/base.py`
- Modify: `tests/unit/test_registry.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_registry.py`:
```python
from squid_tools.core.data_model import FOVPosition


class TestProcessRegion:
    def test_default_process_region_returns_none(self) -> None:
        plugin = DummyPlugin()
        result = plugin.process_region(
            frames={0: np.ones((10, 10))},
            positions=[FOVPosition(fov_index=0, x_mm=0.0, y_mm=0.0)],
            params=DummyParams(),
        )
        assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_registry.py::TestProcessRegion -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Add process_region to ProcessingPlugin ABC**

In `squid_tools/processing/base.py`, add to the `ProcessingPlugin` class:

```python
    def process_region(
        self,
        frames: dict[int, np.ndarray],
        positions: list["FOVPosition"],
        params: BaseModel,
    ) -> np.ndarray | None:
        """Override for spatial plugins (stitching). Default: not spatial."""
        return None
```

Add the TYPE_CHECKING import:
```python
if TYPE_CHECKING:
    from squid_tools.core.data_model import FOVPosition
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_registry.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add squid_tools/processing/base.py tests/unit/test_registry.py
git commit -m "feat: add process_region() to ProcessingPlugin ABC for spatial plugins"
```

---

### Task 4: Namespace Package pyproject.toml Files

**Files:**
- Create: `core/pyproject.toml`
- Create: `viewer/pyproject.toml`
- Create: `processing/flatfield/pyproject.toml`
- Modify: root `pyproject.toml` (becomes meta-package)

Note: For v1 development, we keep the flat source layout and the namespace pyproject.tomls are REFERENCE files showing how each package would be independently installable. The actual development install is still `pip install -e ".[dev]"` from root. The namespace split becomes real when we need independent releases.

- [ ] **Step 1: Create core pyproject.toml**

`core/pyproject.toml`:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "squid-tools-core"
version = "0.1.0"
description = "Core data model and readers for squid-tools"
requires-python = ">=3.10"
dependencies = [
    "pydantic>=2.10",
    "numpy>=1.24",
    "dask[array]>=2024.1",
    "tifffile>=2024.1",
    "pyyaml>=6.0",
    "zarr>=2.16",
]
```

- [ ] **Step 2: Create viewer pyproject.toml**

`viewer/pyproject.toml`:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "squid-tools-viewer"
version = "0.1.0"
description = "Custom vispy+PySide6 viewer for squid-tools"
requires-python = ">=3.10"
dependencies = [
    "squid-tools-core>=0.1.0",
    "vispy>=0.14",
    "PySide6>=6.6",
]
```

- [ ] **Step 3: Create flatfield pyproject.toml**

`processing/flatfield/pyproject.toml`:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "squid-tools-flatfield"
version = "0.1.0"
description = "Flatfield correction processing module for squid-tools"
requires-python = ">=3.10"
dependencies = [
    "squid-tools-core>=0.1.0",
    "scipy>=1.10",
]

[project.entry-points."squid_tools.plugins"]
flatfield = "squid_tools.processing.flatfield.plugin:FlatfieldPlugin"
```

- [ ] **Step 4: Update root pyproject.toml**

Add a comment and entry point for the flatfield plugin:

```toml
[project.entry-points."squid_tools.plugins"]
flatfield = "squid_tools.processing.flatfield.plugin:FlatfieldPlugin"
```

- [ ] **Step 5: Verify install still works**

Run: `pip install -e ".[dev]"`
Run: `python -c "from squid_tools.processing.flatfield.plugin import FlatfieldPlugin; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add core/pyproject.toml viewer/pyproject.toml processing/flatfield/pyproject.toml pyproject.toml
git commit -m "docs: add namespace package pyproject.toml files (reference for future splits)"
```

---

### Task 5: Global QSS Stylesheet

**Files:**
- Create: `squid_tools/gui/style.py`
- Modify: `squid_tools/gui/app.py`
- Create: `tests/unit/test_gui_style.py`

- [ ] **Step 1: Write failing test**

`tests/unit/test_gui_style.py`:
```python
"""Tests for Cephla-branded stylesheet."""

from squid_tools.gui.style import CEPHLA_STYLESHEET, apply_style


class TestStyle:
    def test_stylesheet_is_string(self) -> None:
        assert isinstance(CEPHLA_STYLESHEET, str)
        assert len(CEPHLA_STYLESHEET) > 100

    def test_contains_brand_colors(self) -> None:
        assert "#353535" in CEPHLA_STYLESHEET  # graphite
        assert "#2A82DA" in CEPHLA_STYLESHEET  # cephla blue
        assert "#2a2a2a" in CEPHLA_STYLESHEET  # dark graphite

    def test_apply_style_to_app(self, qtbot) -> None:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            apply_style(app)
            assert app.styleSheet() != ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_gui_style.py -v`

- [ ] **Step 3: Implement style module**

`squid_tools/gui/style.py`:
```python
"""Cephla-branded global stylesheet for squid-tools.

Color palette from cephla-downloads.pages.dev:
  Background primary:   #353535 (graphite)
  Background secondary: #2a2a2a (dark graphite)
  Text primary:         #ffffff (white)
  Text secondary:       #aaaaaa (light gray)
  Text body:            #cccccc (light gray)
  Accent:               #2A82DA (Cephla blue)
  Border:               #444444 (dark gray)

Minimal. The data is the centerpiece, not the chrome.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

CEPHLA_STYLESHEET = """
/* Global */
* {
    font-family: "Segoe UI", "Helvetica Neue", "Arial", sans-serif;
    font-size: 13px;
}

QMainWindow, QWidget {
    background-color: #353535;
    color: #cccccc;
}

/* Labels */
QLabel {
    color: #ffffff;
    background: transparent;
}

/* Buttons */
QPushButton {
    background-color: #2a2a2a;
    color: #cccccc;
    border: 1px solid #444444;
    padding: 6px 16px;
    min-height: 20px;
}
QPushButton:hover {
    border-color: #2A82DA;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #2A82DA;
    color: #ffffff;
}
QPushButton:checked {
    background-color: #2A82DA;
    color: #ffffff;
    border-color: #2A82DA;
}
QPushButton:disabled {
    opacity: 0.4;
    color: #666666;
}

/* Tabs */
QTabWidget::pane {
    border: none;
    background-color: #353535;
}
QTabBar::tab {
    background-color: #2a2a2a;
    color: #aaaaaa;
    padding: 8px 20px;
    border: none;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    color: #ffffff;
    border-bottom: 2px solid #2A82DA;
}
QTabBar::tab:hover {
    color: #ffffff;
}

/* Sliders */
QSlider::groove:horizontal {
    background: #444444;
    height: 4px;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #2A82DA;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}
QSlider::sub-page:horizontal {
    background: #2A82DA;
    border-radius: 2px;
}

/* Checkboxes */
QCheckBox {
    color: #cccccc;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #444444;
    background: #2a2a2a;
}
QCheckBox::indicator:checked {
    background: #2A82DA;
    border-color: #2A82DA;
}

/* Combo boxes */
QComboBox {
    background-color: #2a2a2a;
    color: #cccccc;
    border: 1px solid #444444;
    padding: 4px 8px;
}
QComboBox:hover {
    border-color: #2A82DA;
}
QComboBox::drop-down {
    border: none;
    background: #2a2a2a;
}

/* Spin boxes */
QSpinBox, QDoubleSpinBox {
    background-color: #2a2a2a;
    color: #cccccc;
    border: 1px solid #444444;
    padding: 2px 6px;
}
QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: #2A82DA;
}

/* Splitters */
QSplitter::handle {
    background: #444444;
    width: 1px;
}

/* Scroll bars */
QScrollBar:vertical {
    background: #2a2a2a;
    width: 8px;
}
QScrollBar::handle:vertical {
    background: #444444;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #2A82DA;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

/* Menu bar */
QMenuBar {
    background-color: #2a2a2a;
    color: #cccccc;
}
QMenuBar::item:selected {
    background-color: #2A82DA;
    color: #ffffff;
}
QMenu {
    background-color: #2a2a2a;
    color: #cccccc;
    border: 1px solid #444444;
}
QMenu::item:selected {
    background-color: #2A82DA;
    color: #ffffff;
}

/* Tooltips */
QToolTip {
    background-color: #2a2a2a;
    color: #ffffff;
    border: 1px solid #444444;
    padding: 4px;
}

/* Form layout labels */
QFormLayout QLabel {
    color: #aaaaaa;
}
"""


def apply_style(app: QApplication) -> None:
    """Apply the Cephla-branded stylesheet to the application."""
    app.setStyleSheet(CEPHLA_STYLESHEET)
```

- [ ] **Step 4: Wire into MainWindow**

In `squid_tools/gui/app.py`, in the `main()` function, after creating `QApplication`:
```python
    from squid_tools.gui.style import apply_style
    apply_style(app)
```

Also in `squid_tools/__main__.py`, same location.

- [ ] **Step 5: Run tests**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_gui_style.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add squid_tools/gui/style.py squid_tools/gui/app.py squid_tools/__main__.py tests/unit/test_gui_style.py
git commit -m "feat: Cephla-branded global QSS stylesheet (graphite + blue accent)"
```

---

### Task 6: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `QT_QPA_PLATFORM=offscreen pytest -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Run ruff**

Run: `ruff check squid_tools/ tests/ installer/`
Expected: Clean

- [ ] **Step 3: Verify imports**

Run: `python -c "from squid_tools.processing.base import ProcessingPlugin; print('OK')"`
Run: `python -c "from squid_tools.processing.flatfield.plugin import FlatfieldPlugin; print('OK')"`
Run: `python -c "from squid_tools.gui.style import CEPHLA_STYLESHEET; print('OK')"`
Run: `QT_QPA_PLATFORM=offscreen python -m squid_tools --version`

- [ ] **Step 4: Verify no PyQt5 or napari references remain**

Run: `grep -rn "PyQt5\|from napari\|import napari" squid_tools/ tests/ installer/ --include="*.py"`
Expected: No matches

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "chore: final restructure verification, PySide6 migration complete"
```
