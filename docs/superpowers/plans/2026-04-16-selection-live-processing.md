# Selection Model + Live Processing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add shift+drag FOV selection, refactor processing tabs to toggle + Run button, add `AlgorithmRunner` QThread, extend `ProcessingPlugin` ABC with `run_live()`, retrofit flatfield (calibrate-then-apply) and stitcher (progressive pairwise) with custom live behaviors.

**Architecture:** A `SelectionState` QObject tracks selected FOV indices. `StageCanvas` emits `selection_drawn` on shift+drag. `ProcessingTabs` gets Run buttons alongside toggles. `AlgorithmRunner` runs `plugin.run_live()` in a QThread, emitting progress signals back to the GUI. Existing plugins override `run_live()` for their specific live behaviors.

**Tech Stack:** PySide6 (QThread, QObject, signals), vispy (mouse events, Line visuals), existing `squid_tools.core` and `squid_tools.viewer`

**Spec:** `docs/superpowers/specs/2026-04-16-selection-live-processing-design.md`

---

## File Structure

```
squid_tools/viewer/
├── selection.py             # NEW: SelectionState QObject
├── canvas.py                # MODIFY: selection_drawn signal, drag-box rectangle, border color override
├── widget.py                # MODIFY: wire selection, border colors, helper methods
├── viewport_engine.py       # MODIFY: add all_fov_indices, visible_fov_indices, get_nominal_positions, cache_processed_tile
squid_tools/gui/
├── algorithm_runner.py      # NEW: QThread-based runner
├── processing_tabs.py       # REWRITE: toggle + Run button + status line, auto-run logic
├── app.py                   # MODIFY: create AlgorithmRunner, wire run_requested, pass selection
squid_tools/processing/
├── base.py                  # MODIFY: add run_live() with default implementation
├── flatfield/plugin.py      # MODIFY: override run_live() with calibrate-then-apply
├── stitching/plugin.py      # MODIFY: override run_live() with progressive pairwise
tests/
├── unit/
│   ├── test_selection_state.py          # NEW
│   ├── test_canvas_selection.py         # NEW
│   ├── test_algorithm_runner.py         # NEW
│   ├── test_processing_tabs_runbutton.py # NEW (replaces test_processing_toggles.py content)
│   ├── test_plugin_run_live.py          # NEW (default run_live contract)
│   ├── test_flatfield_run_live.py       # NEW
│   └── test_stitcher_run_live.py        # NEW
└── integration/
    └── test_selection_workflow.py       # NEW (end-to-end selection + Run)
```

---

### Task 1: SelectionState

**Files:**
- Create: `squid_tools/viewer/selection.py`
- Create: `tests/unit/test_selection_state.py`

- [ ] **Step 1: Write failing test**

`tests/unit/test_selection_state.py`:
```python
"""Tests for SelectionState."""

from pytestqt.qtbot import QtBot

from squid_tools.viewer.selection import SelectionState


class TestSelectionState:
    def test_starts_empty(self, qtbot: QtBot) -> None:
        state = SelectionState()
        assert state.is_empty()
        assert state.selected == set()

    def test_set_selection(self, qtbot: QtBot) -> None:
        state = SelectionState()
        state.set_selection({0, 1, 2})
        assert state.selected == {0, 1, 2}
        assert not state.is_empty()

    def test_selected_returns_copy(self, qtbot: QtBot) -> None:
        state = SelectionState()
        state.set_selection({0, 1, 2})
        s = state.selected
        s.add(99)
        assert state.selected == {0, 1, 2}

    def test_set_selection_emits_signal(self, qtbot: QtBot) -> None:
        state = SelectionState()
        with qtbot.waitSignal(state.selection_changed, timeout=500) as blocker:
            state.set_selection({5, 7})
        assert blocker.args[0] == {5, 7}

    def test_same_selection_no_emit(self, qtbot: QtBot) -> None:
        state = SelectionState()
        state.set_selection({0, 1})
        # Second call with identical set should NOT emit
        received = []
        state.selection_changed.connect(lambda s: received.append(s))
        state.set_selection({0, 1})
        assert received == []

    def test_clear(self, qtbot: QtBot) -> None:
        state = SelectionState()
        state.set_selection({0, 1})
        with qtbot.waitSignal(state.selection_changed, timeout=500):
            state.clear()
        assert state.is_empty()

    def test_clear_when_empty_no_emit(self, qtbot: QtBot) -> None:
        state = SelectionState()
        received = []
        state.selection_changed.connect(lambda s: received.append(s))
        state.clear()
        assert received == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_selection_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'squid_tools.viewer.selection'`

- [ ] **Step 3: Implement SelectionState**

`squid_tools/viewer/selection.py`:
```python
"""Selection state for FOV selection in the viewer.

Thread-safe via Qt signals. The set of selected FOV indices is
the single source of truth. Widgets subscribe to selection_changed.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class SelectionState(QObject):
    """Tracks currently selected FOV indices."""

    selection_changed = Signal(set)  # set[int] of FOV indices

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._selected: set[int] = set()

    @property
    def selected(self) -> set[int]:
        """Return a copy of the currently selected indices."""
        return self._selected.copy()

    def set_selection(self, indices: set[int]) -> None:
        """Replace the current selection. Emit if changed."""
        new = set(indices)
        if new == self._selected:
            return
        self._selected = new
        self.selection_changed.emit(self.selected)

    def clear(self) -> None:
        """Clear the selection. Emit if it was non-empty."""
        if not self._selected:
            return
        self._selected = set()
        self.selection_changed.emit(self.selected)

    def is_empty(self) -> bool:
        return len(self._selected) == 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_selection_state.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add squid_tools/viewer/selection.py tests/unit/test_selection_state.py
git commit -m "feat: SelectionState QObject for FOV selection tracking"
```

---

### Task 2: StageCanvas selection support (drag-box + border colors)

**Files:**
- Modify: `squid_tools/viewer/canvas.py`
- Create: `tests/unit/test_canvas_selection.py`

- [ ] **Step 1: Write failing test**

`tests/unit/test_canvas_selection.py`:
```python
"""Tests for StageCanvas selection features."""

import numpy as np

from squid_tools.viewer.canvas import StageCanvas
from squid_tools.viewer.viewport_engine import VisibleTile


def _make_tile(fov_index: int, x_mm: float, y_mm: float) -> VisibleTile:
    return VisibleTile(
        fov_index=fov_index,
        x_mm=x_mm, y_mm=y_mm,
        width_mm=1.0, height_mm=1.0,
        data=np.zeros((32, 32), dtype=np.float32),
    )


class TestCanvasSelection:
    def test_selection_drawn_signal_exists(self) -> None:
        canvas = StageCanvas()
        assert hasattr(canvas, "selection_drawn")

    def test_set_selected_ids_updates_border_colors(self) -> None:
        canvas = StageCanvas()
        tiles = [_make_tile(0, 0.0, 0.0), _make_tile(1, 1.0, 0.0)]
        canvas.render_tiles(tiles)
        # Mark fov 0 as selected
        canvas.set_selected_ids({0})
        # The border for fov 0 should now be Cephla-blue, fov 1 still yellow
        assert canvas._selected_ids == {0}

    def test_set_selected_ids_empty_clears(self) -> None:
        canvas = StageCanvas()
        tiles = [_make_tile(0, 0.0, 0.0)]
        canvas.render_tiles(tiles)
        canvas.set_selected_ids({0})
        canvas.set_selected_ids(set())
        assert canvas._selected_ids == set()

    def test_selected_border_color_differs(self) -> None:
        # Cannot easily read vispy Line color programmatically in headless tests,
        # so we verify the helper returns the expected color strings.
        canvas = StageCanvas()
        assert canvas._border_color_for(fov_index=5, selected_ids={5}) == "#2A82DA"
        assert canvas._border_color_for(fov_index=5, selected_ids=set()) == "yellow"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_canvas_selection.py -v`
Expected: FAIL (missing `selection_drawn`, `set_selected_ids`, `_selected_ids`, `_border_color_for`)

- [ ] **Step 3: Add selection support to StageCanvas**

Modify `squid_tools/viewer/canvas.py`. Add these changes:

At the top of imports (if not already present):
```python
from PySide6.QtCore import QObject, Signal
```

Change `StageCanvas` to inherit from `QObject` so it can emit signals. Replace class header:

```python
class StageCanvas(QObject):
    """Renders tiles in mm stage coordinates."""

    selection_drawn = Signal(tuple)  # (x_min_mm, y_min_mm, x_max_mm, y_max_mm)

    def __init__(self) -> None:
        super().__init__()
        self._canvas = SceneCanvas(keys="interactive", show=False, bgcolor="#000000")
        self._view = self._canvas.central_widget.add_view()
        self._view.camera = PanZoomCamera(aspect=1)

        self._tiles: dict[int, Image] = {}
        self._borders: dict[int, Line] = {}
        self._borders_visible = True
        self._clim: tuple[float, float] | None = None
        self._cmap: str = "grays"

        # Selection state (canvas just tracks IDs; ViewerWidget owns real state)
        self._selected_ids: set[int] = set()

        # Drag-box state
        self._drag_start: tuple[float, float] | None = None
        self._drag_rect: Line | None = None

        # Wire mouse events
        self._canvas.events.mouse_press.connect(self._on_mouse_press)
        self._canvas.events.mouse_move.connect(self._on_mouse_move)
        self._canvas.events.mouse_release.connect(self._on_mouse_release)
```

Add methods (at end of class):

```python
    def set_selected_ids(self, ids: set[int]) -> None:
        """Update which FOVs should be drawn with selection borders."""
        self._selected_ids = set(ids)
        # Re-color existing borders
        for fov_id, line in self._borders.items():
            color = self._border_color_for(fov_id, self._selected_ids)
            line.set_data(color=color)

    @staticmethod
    def _border_color_for(fov_index: int, selected_ids: set[int]) -> str:
        """Return the border color string for a given FOV."""
        return "#2A82DA" if fov_index in selected_ids else "yellow"

    def _scene_coords(self, event_pos: tuple[float, float]) -> tuple[float, float]:
        """Convert pixel event coords to scene (mm) coords."""
        tr = self._canvas.scene.node_transform(self._view.scene)
        mapped = tr.map(event_pos)
        return float(mapped[0]), float(mapped[1])

    def _on_mouse_press(self, event: object) -> None:
        modifiers = getattr(event, "modifiers", ())
        from vispy.util.keys import SHIFT
        if SHIFT in modifiers:
            self._drag_start = self._scene_coords(event.pos)
            # Disable camera interaction while drag-selecting
            self._view.camera.interactive = False

    def _on_mouse_move(self, event: object) -> None:
        if self._drag_start is None:
            return
        x0, y0 = self._drag_start
        x1, y1 = self._scene_coords(event.pos)
        self._update_drag_rect(x0, y0, x1, y1)

    def _on_mouse_release(self, event: object) -> None:
        if self._drag_start is None:
            return
        x0, y0 = self._drag_start
        x1, y1 = self._scene_coords(event.pos)
        x_min, x_max = min(x0, x1), max(x0, x1)
        y_min, y_max = min(y0, y1), max(y0, y1)
        # Remove the drag rectangle visual
        if self._drag_rect is not None:
            self._drag_rect.parent = None
            self._drag_rect = None
        self._drag_start = None
        self._view.camera.interactive = True
        # Emit selection bounds
        self.selection_drawn.emit((x_min, y_min, x_max, y_max))

    def _update_drag_rect(
        self, x0: float, y0: float, x1: float, y1: float,
    ) -> None:
        corners = np.array([
            [x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0],
        ], dtype=np.float32)
        if self._drag_rect is None:
            self._drag_rect = Line(
                pos=corners, color="#2A82DA", width=1,
                connect="strip", parent=self._view.scene,
            )
            self._drag_rect.order = -2
        else:
            self._drag_rect.set_data(pos=corners)
```

Also modify `_ensure_border()` (existing method) to use the new color logic:

Find this block in `_ensure_border`:
```python
        if tile.fov_index in self._borders:
            self._borders[tile.fov_index].set_data(pos=corners)
        else:
            line = Line(
                pos=corners, color="yellow", width=2,
                connect="strip", parent=self._view.scene,
            )
            line.order = -1
            self._borders[tile.fov_index] = line

        self._borders[tile.fov_index].visible = self._borders_visible
```

Replace with:
```python
        color = self._border_color_for(tile.fov_index, self._selected_ids)
        if tile.fov_index in self._borders:
            self._borders[tile.fov_index].set_data(pos=corners, color=color)
        else:
            line = Line(
                pos=corners, color=color, width=2,
                connect="strip", parent=self._view.scene,
            )
            line.order = -1
            self._borders[tile.fov_index] = line

        self._borders[tile.fov_index].visible = self._borders_visible
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_canvas_selection.py -v`
Expected: 4 passed

- [ ] **Step 5: Run full suite to confirm no regressions**

Run: `QT_QPA_PLATFORM=offscreen pytest -q`
Expected: All previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add squid_tools/viewer/canvas.py tests/unit/test_canvas_selection.py
git commit -m "feat: StageCanvas drag-box selection and border color override"
```

---

### Task 3: ViewportEngine helpers

**Files:**
- Modify: `squid_tools/viewer/viewport_engine.py`
- Modify: `tests/unit/test_viewport_engine.py`

- [ ] **Step 1: Add failing tests for new methods**

Append to `tests/unit/test_viewport_engine.py`:
```python
class TestViewportEngineHelpers:
    def test_all_fov_indices(self, tmp_path):
        from pathlib import Path
        from squid_tools.viewer.viewport_engine import ViewportEngine
        from tests.fixtures.generate_fixtures import create_individual_acquisition

        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        indices = engine.all_fov_indices()
        assert indices == {0, 1, 2, 3}

    def test_visible_fov_indices_uses_camera(self, tmp_path):
        from pathlib import Path
        from squid_tools.viewer.viewport_engine import ViewportEngine
        from tests.fixtures.generate_fixtures import create_individual_acquisition

        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        # Entire bounding box → all 4 FOVs
        bb = engine.bounding_box()
        visible = engine.visible_fov_indices(*bb)
        assert visible == {0, 1, 2, 3}

    def test_get_nominal_positions(self, tmp_path):
        from pathlib import Path
        from squid_tools.viewer.viewport_engine import ViewportEngine
        from tests.fixtures.generate_fixtures import create_individual_acquisition

        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        positions = engine.get_nominal_positions({0, 1})
        assert 0 in positions and 1 in positions
        assert isinstance(positions[0], tuple)
        assert len(positions[0]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_viewport_engine.py::TestViewportEngineHelpers -v`
Expected: FAIL (methods don't exist)

- [ ] **Step 3: Implement helpers**

Add these methods to `ViewportEngine` in `squid_tools/viewer/viewport_engine.py`:

```python
    def all_fov_indices(self) -> set[int]:
        """All FOV indices in the currently loaded region."""
        if self._acquisition is None or self._region == "":
            return set()
        region_obj = self._acquisition.regions.get(self._region)
        if region_obj is None:
            return set()
        return {fov.fov_index for fov in region_obj.fovs}

    def visible_fov_indices(
        self, x_min: float, y_min: float, x_max: float, y_max: float,
    ) -> set[int]:
        """FOV indices whose tiles intersect the given viewport (mm)."""
        if self._index is None:
            return set()
        visible = self._index.query(x_min, y_min, x_max, y_max)
        return {fov.fov_index for fov in visible}

    def get_nominal_positions(
        self, indices: set[int],
    ) -> dict[int, tuple[float, float]]:
        """Return {fov_index: (x_mm, y_mm)} for the given indices.

        Returns nominal positions from coordinates.csv, ignoring any
        position overrides from registration.
        """
        if self._acquisition is None or self._region == "":
            return {}
        region_obj = self._acquisition.regions.get(self._region)
        if region_obj is None:
            return {}
        return {
            fov.fov_index: (fov.x_mm, fov.y_mm)
            for fov in region_obj.fovs
            if fov.fov_index in indices
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_viewport_engine.py::TestViewportEngineHelpers -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add squid_tools/viewer/viewport_engine.py tests/unit/test_viewport_engine.py
git commit -m "feat: ViewportEngine helpers (all_fov_indices, visible_fov_indices, get_nominal_positions)"
```

---

### Task 4: ProcessingPlugin.run_live() default

**Files:**
- Modify: `squid_tools/processing/base.py`
- Create: `tests/unit/test_plugin_run_live.py`

- [ ] **Step 1: Write failing test**

`tests/unit/test_plugin_run_live.py`:
```python
"""Tests for ProcessingPlugin.run_live() default implementation."""

from pathlib import Path

import numpy as np
from pydantic import BaseModel

from squid_tools.core.data_model import Acquisition
from squid_tools.processing.base import ProcessingPlugin
from squid_tools.viewer.viewport_engine import ViewportEngine
from tests.fixtures.generate_fixtures import create_individual_acquisition


class NoopParams(BaseModel):
    pass


class NoopPlugin(ProcessingPlugin):
    name = "Noop"
    category = "correction"
    requires_gpu = False

    def parameters(self) -> type[BaseModel]:
        return NoopParams

    def validate(self, acq: Acquisition) -> list[str]:
        return []

    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        return frames  # identity

    def default_params(self, optical) -> BaseModel:
        return NoopParams()

    def test_cases(self) -> list[dict]:
        return []


class TestRunLiveDefault:
    def test_run_live_exists(self) -> None:
        plugin = NoopPlugin()
        assert hasattr(plugin, "run_live")

    def test_run_live_calls_progress(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = NoopPlugin()

        calls = []

        def progress(phase: str, cur: int, total: int) -> None:
            calls.append((phase, cur, total))

        plugin.run_live(
            selection={0, 1},
            engine=engine,
            params=NoopParams(),
            progress=progress,
        )
        # At least one progress call, last current equals total
        assert len(calls) >= 1
        last = calls[-1]
        assert last[1] == last[2]

    def test_run_live_none_selection_uses_all(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = NoopPlugin()

        calls = []
        def progress(phase: str, cur: int, total: int) -> None:
            calls.append((phase, cur, total))

        plugin.run_live(
            selection=None, engine=engine,
            params=NoopParams(), progress=progress,
        )
        # Total should equal 4 (nx*ny for 2x2 grid)
        assert calls[-1][2] == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_plugin_run_live.py -v`
Expected: FAIL (`run_live` does not exist)

- [ ] **Step 3: Implement default `run_live()` on the ABC**

Add to `squid_tools/processing/base.py`:

```python
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from squid_tools.viewer.viewport_engine import ViewportEngine
```

Add method to the `ProcessingPlugin` class (not abstract — default impl provided):

```python
    def run_live(
        self,
        selection: set[int] | None,
        engine: "ViewportEngine",
        params: BaseModel,
        progress: Callable[[str, int, int], None],
    ) -> None:
        """Run this plugin live with progress feedback.

        Default: iterate the selection (or all FOVs if None), call process()
        on each tile, emit progress per tile.

        Plugins override this for custom live behavior (calibrate-then-apply,
        progressive pairwise registration, etc.).
        """
        indices = selection if selection else engine.all_fov_indices()
        indices_list = sorted(indices)
        total = max(len(indices_list), 1)
        progress("Processing", 0, total)
        for i, fov in enumerate(indices_list):
            frame = engine.get_raw_frame(fov, z=0, channel=0, timepoint=0)
            _ = self.process(frame, params)
            progress("Processing", i + 1, total)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_plugin_run_live.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add squid_tools/processing/base.py tests/unit/test_plugin_run_live.py
git commit -m "feat: ProcessingPlugin.run_live() default tile-by-tile implementation"
```

---

### Task 5: AlgorithmRunner (QThread runner)

**Files:**
- Create: `squid_tools/gui/algorithm_runner.py`
- Create: `tests/unit/test_algorithm_runner.py`

- [ ] **Step 1: Write failing test**

`tests/unit/test_algorithm_runner.py`:
```python
"""Tests for AlgorithmRunner."""

from pathlib import Path

import numpy as np
from pydantic import BaseModel
from pytestqt.qtbot import QtBot

from squid_tools.core.data_model import Acquisition
from squid_tools.gui.algorithm_runner import AlgorithmRunner
from squid_tools.processing.base import ProcessingPlugin
from squid_tools.viewer.viewport_engine import ViewportEngine
from tests.fixtures.generate_fixtures import create_individual_acquisition


class _Params(BaseModel):
    pass


class _InstantPlugin(ProcessingPlugin):
    name = "Instant"
    category = "correction"
    requires_gpu = False

    def parameters(self) -> type[BaseModel]:
        return _Params

    def validate(self, acq: Acquisition) -> list[str]:
        return []

    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        return frames

    def default_params(self, optical) -> BaseModel:
        return _Params()

    def test_cases(self) -> list[dict]:
        return []


class _FailingPlugin(_InstantPlugin):
    name = "Failing"

    def run_live(self, selection, engine, params, progress):
        raise RuntimeError("boom")


class TestAlgorithmRunner:
    def test_run_emits_complete(self, qtbot: QtBot, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = _InstantPlugin()
        runner = AlgorithmRunner()

        with qtbot.waitSignal(runner.run_complete, timeout=5000):
            runner.run(plugin=plugin, selection={0, 1}, engine=engine, params=_Params())

    def test_run_emits_progress(self, qtbot: QtBot, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = _InstantPlugin()
        runner = AlgorithmRunner()

        progress_calls: list[tuple] = []
        runner.progress_updated.connect(lambda *a: progress_calls.append(a))

        with qtbot.waitSignal(runner.run_complete, timeout=5000):
            runner.run(plugin=plugin, selection={0, 1}, engine=engine, params=_Params())

        assert len(progress_calls) >= 1

    def test_run_failure_emits_run_failed(self, qtbot: QtBot, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = _FailingPlugin()
        runner = AlgorithmRunner()

        with qtbot.waitSignal(runner.run_failed, timeout=5000) as blocker:
            runner.run(plugin=plugin, selection={0}, engine=engine, params=_Params())
        # First arg is plugin_name, second is error message
        assert blocker.args[0] == "Failing"
        assert "boom" in blocker.args[1]

    def test_second_run_while_busy_is_rejected(self, qtbot: QtBot, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = _InstantPlugin()
        runner = AlgorithmRunner()

        # Kick off first run
        runner.run(plugin=plugin, selection={0}, engine=engine, params=_Params())
        # Second run immediately after should return False
        accepted = runner.run(plugin=plugin, selection={1}, engine=engine, params=_Params())
        assert accepted is False
        qtbot.waitUntil(lambda: not runner.is_running(), timeout=5000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_algorithm_runner.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Implement AlgorithmRunner**

`squid_tools/gui/algorithm_runner.py`:
```python
"""Background thread runner for ProcessingPlugin.run_live().

Runs plugin live execution in a QThread. Marshals progress
signals back to the GUI thread via Qt.
"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, Signal
from pydantic import BaseModel

if TYPE_CHECKING:
    from squid_tools.processing.base import ProcessingPlugin
    from squid_tools.viewer.viewport_engine import ViewportEngine


class _Worker(QObject):
    """Does the actual work on a background thread."""

    progress_updated = Signal(str, str, int, int)  # plugin_name, phase, current, total
    run_complete = Signal(str, int)                # plugin_name, tiles_processed
    run_failed = Signal(str, str)                  # plugin_name, error_message

    def __init__(
        self,
        plugin: "ProcessingPlugin",
        selection: set[int] | None,
        engine: "ViewportEngine",
        params: BaseModel,
    ) -> None:
        super().__init__()
        self._plugin = plugin
        self._selection = selection
        self._engine = engine
        self._params = params
        self._tiles_processed = 0

    def run(self) -> None:
        name = self._plugin.name
        try:
            def progress_cb(phase: str, current: int, total: int) -> None:
                self._tiles_processed = current
                self.progress_updated.emit(name, phase, current, total)

            self._plugin.run_live(
                selection=self._selection,
                engine=self._engine,
                params=self._params,
                progress=progress_cb,
            )
            self.run_complete.emit(name, self._tiles_processed)
        except Exception as exc:  # noqa: BLE001 — surface to GUI
            tb = traceback.format_exc()
            self.run_failed.emit(name, f"{exc}\n{tb}")


class AlgorithmRunner(QObject):
    """Public API: runs plugins in a background thread, emits progress signals."""

    progress_updated = Signal(str, str, int, int)  # plugin_name, phase, current, total
    run_complete = Signal(str, int)                # plugin_name, tiles_processed
    run_failed = Signal(str, str)                  # plugin_name, error_message

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _Worker | None = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def run(
        self,
        plugin: "ProcessingPlugin",
        selection: set[int] | None,
        engine: "ViewportEngine",
        params: BaseModel,
    ) -> bool:
        """Start a plugin run. Returns True if accepted, False if another is in flight."""
        if self.is_running():
            return False
        thread = QThread()
        worker = _Worker(plugin, selection, engine, params)
        worker.moveToThread(thread)
        worker.progress_updated.connect(self.progress_updated)
        worker.run_complete.connect(self._on_complete)
        worker.run_failed.connect(self._on_failed)
        thread.started.connect(worker.run)
        thread.start()
        self._thread = thread
        self._worker = worker
        return True

    def _on_complete(self, plugin_name: str, tiles_processed: int) -> None:
        self.run_complete.emit(plugin_name, tiles_processed)
        self._cleanup()

    def _on_failed(self, plugin_name: str, error_message: str) -> None:
        self.run_failed.emit(plugin_name, error_message)
        self._cleanup()

    def _cleanup(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
            self._worker = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_algorithm_runner.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add squid_tools/gui/algorithm_runner.py tests/unit/test_algorithm_runner.py
git commit -m "feat: AlgorithmRunner QThread for background plugin execution with progress signals"
```

---

### Task 6: Rewrite ProcessingTabs with Toggle + Run + Status

**Files:**
- Modify: `squid_tools/gui/processing_tabs.py`
- Create: `tests/unit/test_processing_tabs_runbutton.py`

- [ ] **Step 1: Write failing test**

`tests/unit/test_processing_tabs_runbutton.py`:
```python
"""Tests for toggle + Run button + status processing tabs."""

import numpy as np
from pydantic import BaseModel
from pytestqt.qtbot import QtBot

from squid_tools.core.registry import PluginRegistry
from squid_tools.gui.processing_tabs import ProcessingTabs
from squid_tools.processing.base import ProcessingPlugin


class _Params(BaseModel):
    value: float = 1.0


class _Plugin(ProcessingPlugin):
    name = "Demo"
    category = "correction"
    requires_gpu = False

    def parameters(self) -> type[BaseModel]:
        return _Params

    def validate(self, acq) -> list[str]:
        return []

    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        return frames

    def default_params(self, optical) -> BaseModel:
        return _Params()

    def test_cases(self) -> list[dict]:
        return []


class TestProcessingTabsRunButton:
    def test_has_toggle_and_run_button(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        registry.register(_Plugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        from PySide6.QtWidgets import QCheckBox, QPushButton
        tab = tabs.widget(0)
        assert tab.findChildren(QCheckBox)
        assert tab.findChildren(QPushButton)

    def test_run_requested_signal(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        registry.register(_Plugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        with qtbot.waitSignal(tabs.run_requested, timeout=500) as blocker:
            tabs.click_run("Demo")
        assert blocker.args[0] == "Demo"
        # Second arg is params dict
        assert isinstance(blocker.args[1], dict)

    def test_set_status(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        registry.register(_Plugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        tabs.set_status("Demo", "Calibrating...")
        assert tabs.status_text("Demo") == "Calibrating..."

    def test_auto_run_on_first_toggle(self, qtbot: QtBot) -> None:
        """First toggle ON of an uncalibrated plugin should emit run_requested."""
        registry = PluginRegistry()
        registry.register(_Plugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        with qtbot.waitSignal(tabs.run_requested, timeout=500):
            tabs.set_toggle("Demo", True)

    def test_second_toggle_on_after_calibration_no_autorun(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        registry.register(_Plugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        # Mark as calibrated
        tabs.mark_calibrated("Demo")

        received = []
        tabs.run_requested.connect(lambda n, p: received.append(n))
        # Turn off then on — should NOT trigger run_requested
        tabs.set_toggle("Demo", False)
        tabs.set_toggle("Demo", True)
        assert received == []

    def test_toggle_changed_signal_still_emitted(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        registry.register(_Plugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        tabs.mark_calibrated("Demo")  # prevent auto-run
        with qtbot.waitSignal(tabs.toggle_changed, timeout=500) as blocker:
            tabs.set_toggle("Demo", True)
        assert blocker.args == ["Demo", True]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_processing_tabs_runbutton.py -v`
Expected: FAIL (missing signals/methods)

- [ ] **Step 3: Rewrite ProcessingTabs**

Replace `squid_tools/gui/processing_tabs.py`:
```python
"""Processing tabs with toggle + Run button + status line per plugin.

Toggle = enable algorithm in the active pipeline (persistent).
Run    = trigger one-time calibration / computation (expensive).
Status = shows the current state ("Not calibrated" / "Applied to N tiles").

First toggle ON auto-triggers Run (so the user doesn't need to click twice
on first use).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from squid_tools.core.registry import PluginRegistry
from squid_tools.processing.base import ProcessingPlugin


class ProcessingTabs(QTabWidget):
    """Tab widget: toggle + Run button + status per plugin."""

    toggle_changed = Signal(str, bool)     # (plugin_name, is_active)
    run_requested = Signal(str, object)    # (plugin_name, params_dict)

    def __init__(
        self,
        registry: PluginRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = registry
        self._plugin_tabs: dict[str, _PluginTab] = {}
        self._calibrated: dict[str, bool] = {}

        for plugin in registry.list_all():
            tab = _PluginTab(plugin, self)
            tab.toggled.connect(
                lambda active, name=plugin.name: self._on_toggle(name, active)
            )
            tab.run_clicked.connect(
                lambda name=plugin.name: self._on_run_click(name)
            )
            self.addTab(tab, plugin.name)
            self._plugin_tabs[plugin.name] = tab
            self._calibrated[plugin.name] = False

    def set_toggle(self, plugin_name: str, active: bool) -> None:
        """Programmatically toggle a plugin."""
        if plugin_name in self._plugin_tabs:
            self._plugin_tabs[plugin_name].set_active(active)

    def is_active(self, plugin_name: str) -> bool:
        if plugin_name in self._plugin_tabs:
            return self._plugin_tabs[plugin_name].is_active()
        return False

    def active_plugin_names(self) -> list[str]:
        return [
            name for name, tab in self._plugin_tabs.items() if tab.is_active()
        ]

    def get_params(self, plugin_name: str) -> dict[str, Any]:
        if plugin_name in self._plugin_tabs:
            return self._plugin_tabs[plugin_name].get_params()
        return {}

    def set_status(self, plugin_name: str, text: str) -> None:
        if plugin_name in self._plugin_tabs:
            self._plugin_tabs[plugin_name].set_status(text)

    def status_text(self, plugin_name: str) -> str:
        if plugin_name in self._plugin_tabs:
            return self._plugin_tabs[plugin_name].status_text()
        return ""

    def mark_calibrated(self, plugin_name: str) -> None:
        """Record that this plugin has completed its calibration."""
        self._calibrated[plugin_name] = True

    def click_run(self, plugin_name: str) -> None:
        """Programmatically click the Run button."""
        if plugin_name in self._plugin_tabs:
            self._plugin_tabs[plugin_name].click_run()

    def _on_toggle(self, plugin_name: str, active: bool) -> None:
        self.toggle_changed.emit(plugin_name, active)
        # Auto-run on first toggle ON (not yet calibrated)
        if active and not self._calibrated.get(plugin_name, False):
            self._emit_run(plugin_name)

    def _on_run_click(self, plugin_name: str) -> None:
        self._emit_run(plugin_name)

    def _emit_run(self, plugin_name: str) -> None:
        params = self.get_params(plugin_name)
        self.run_requested.emit(plugin_name, params)


class _PluginTab(QWidget):
    """Tab for one plugin: toggle + params + Run button + status line."""

    toggled = Signal(bool)
    run_clicked = Signal()

    def __init__(
        self,
        plugin: ProcessingPlugin,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._plugin = plugin
        self._param_widgets: dict[str, QWidget] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Toggle row
        toggle_row = QHBoxLayout()
        self._toggle = QCheckBox(f"Enable {plugin.name} in pipeline")
        self._toggle.setToolTip(
            f"Enable {plugin.name}. First enable auto-triggers calibration."
        )
        self._toggle.toggled.connect(self.toggled.emit)
        toggle_row.addWidget(self._toggle)
        toggle_row.addStretch()
        layout.addLayout(toggle_row)

        # Parameter widgets
        form = QFormLayout()
        params_cls = plugin.parameters()
        for field_name, field_info in params_cls.model_fields.items():
            annotation = field_info.annotation
            default = field_info.default
            widget: QWidget

            if annotation is float:
                spin = QDoubleSpinBox()
                spin.setRange(-1e6, 1e6)
                spin.setDecimals(3)
                if isinstance(default, (int, float)):
                    spin.setValue(float(default))
                spin.setToolTip(field_info.description or field_name)
                widget = spin
            elif annotation is int:
                spin_int = QSpinBox()
                spin_int.setRange(0, 100000)
                if isinstance(default, int):
                    spin_int.setValue(default)
                spin_int.setToolTip(field_info.description or field_name)
                widget = spin_int
            else:
                continue

            self._param_widgets[field_name] = widget
            form.addRow(field_name, widget)
        layout.addLayout(form)

        # Run button + status
        button_row = QHBoxLayout()
        self._run_button = QPushButton("Calibrate / Compute")
        self._run_button.setToolTip(
            f"Run {plugin.name}'s calibration / computation on the current selection "
            "(or all FOVs if nothing selected)."
        )
        self._run_button.clicked.connect(self.run_clicked.emit)
        button_row.addWidget(self._run_button)
        button_row.addStretch()
        layout.addLayout(button_row)

        self._status_label = QLabel("Not calibrated")
        self._status_label.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(self._status_label)

        layout.addStretch()

    def set_active(self, active: bool) -> None:
        self._toggle.setChecked(active)

    def is_active(self) -> bool:
        return self._toggle.isChecked()

    def set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def status_text(self) -> str:
        return self._status_label.text()

    def click_run(self) -> None:
        self._run_button.click()

    def get_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {}
        for name, widget in self._param_widgets.items():
            if isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                params[name] = widget.value()
        return params
```

- [ ] **Step 2b: Handle existing test_processing_toggles.py**

Delete the now-obsolete file (its behavior is superseded):

```bash
rm tests/unit/test_processing_toggles.py
```

- [ ] **Step 3: Run new tests**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_processing_tabs_runbutton.py tests/unit/test_gui_processing_tabs.py -v`
Expected: Both pass.

If `test_gui_processing_tabs.py` has tests that assumed the old interface (no Run button), update them or delete tests that no longer apply — minimal change: the tests should check that a QCheckBox and a QPushButton exist per tab.

- [ ] **Step 4: Run full suite**

Run: `QT_QPA_PLATFORM=offscreen pytest -q`
Expected: All green.

- [ ] **Step 5: Commit**

```bash
git add squid_tools/gui/processing_tabs.py tests/unit/test_processing_tabs_runbutton.py tests/unit/test_gui_processing_tabs.py
git rm tests/unit/test_processing_toggles.py
git commit -m "feat: processing tabs get Run button and status line; auto-run on first toggle"
```

---

### Task 7: Wire ViewerWidget selection end-to-end

**Files:**
- Modify: `squid_tools/viewer/widget.py`
- Create: `tests/integration/test_selection_workflow.py`

- [ ] **Step 1: Write failing integration test**

`tests/integration/test_selection_workflow.py`:
```python
"""End-to-end test of shift+drag selection and border recoloring."""

from pathlib import Path

from pytestqt.qtbot import QtBot

from squid_tools.viewer.widget import ViewerWidget
from tests.fixtures.generate_fixtures import create_individual_acquisition


class TestSelectionWorkflow:
    def test_viewer_has_selection_state(self, qtbot: QtBot, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=3, ny=3, nz=1, nc=1, nt=1,
        )
        viewer = ViewerWidget()
        qtbot.addWidget(viewer)
        viewer.load_acquisition(acq_path, region="0")
        assert hasattr(viewer, "selection")

    def test_selection_drawn_updates_selection(self, qtbot: QtBot, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        viewer = ViewerWidget()
        qtbot.addWidget(viewer)
        viewer.load_acquisition(acq_path, region="0")

        # Pretend the canvas emitted a selection_drawn covering the entire stage
        bb = viewer._engine.bounding_box()
        viewer._on_selection_drawn(bb)
        # All 4 FOVs should now be selected
        assert viewer.selection.selected == {0, 1, 2, 3}

    def test_empty_rectangle_clears_selection(self, qtbot: QtBot, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        viewer = ViewerWidget()
        qtbot.addWidget(viewer)
        viewer.load_acquisition(acq_path, region="0")

        # First select all
        bb = viewer._engine.bounding_box()
        viewer._on_selection_drawn(bb)
        # Then draw rectangle that intersects no tiles (far away)
        viewer._on_selection_drawn((1000.0, 1000.0, 1001.0, 1001.0))
        assert viewer.selection.is_empty()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/integration/test_selection_workflow.py -v`
Expected: FAIL (`selection` attribute missing)

- [ ] **Step 3: Wire selection into ViewerWidget**

Modify `squid_tools/viewer/widget.py`. Add the import at the top:
```python
from squid_tools.viewer.selection import SelectionState
```

In `ViewerWidget.__init__`, after creating `self._canvas` and `self._engine`, add:
```python
        self.selection = SelectionState(self)
        self._canvas.selection_drawn.connect(self._on_selection_drawn)
        self.selection.selection_changed.connect(self._on_selection_changed)
```

Add the two handler methods to `ViewerWidget`:
```python
    def _on_selection_drawn(
        self, rect: tuple[float, float, float, float],
    ) -> None:
        """Shift+drag released. Convert mm rectangle to FOV indices."""
        if not self._engine.is_loaded():
            return
        x_min, y_min, x_max, y_max = rect
        # Tiny rectangles = clear selection
        if abs(x_max - x_min) < 1e-6 or abs(y_max - y_min) < 1e-6:
            self.selection.clear()
            return
        visible = self._engine.visible_fov_indices(x_min, y_min, x_max, y_max)
        self.selection.set_selection(visible)

    def _on_selection_changed(self, selected: set) -> None:
        """Selection changed. Update canvas border colors."""
        self._canvas.set_selected_ids(selected)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/integration/test_selection_workflow.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add squid_tools/viewer/widget.py tests/integration/test_selection_workflow.py
git commit -m "feat: wire SelectionState into ViewerWidget; drag-box updates selection and border colors"
```

---

### Task 8: Wire AlgorithmRunner into MainWindow

**Files:**
- Modify: `squid_tools/gui/app.py`

- [ ] **Step 1: Modify MainWindow to use AlgorithmRunner**

In `squid_tools/gui/app.py`:

1. Add imports at top:
```python
from squid_tools.gui.algorithm_runner import AlgorithmRunner
```

2. In `MainWindow.__init__`, after the log panel is created, add:
```python
        # Algorithm runner (background thread)
        self._algorithm_runner = AlgorithmRunner(self)
        self._algorithm_runner.progress_updated.connect(self._on_run_progress)
        self._algorithm_runner.run_complete.connect(self._on_run_complete)
        self._algorithm_runner.run_failed.connect(self._on_run_failed)
```

3. Connect the new `run_requested` signal in `processing_tabs`:
```python
        self.processing_tabs.run_requested.connect(self._on_run_requested_tab)
```

4. Add these methods:
```python
    def _on_run_requested_tab(self, plugin_name: str, params_dict: dict) -> None:
        """Run a plugin on the current selection."""
        if self.controller.acquisition is None:
            self.log_panel.log(f"[{plugin_name}] No acquisition loaded.")
            self.processing_tabs.set_status(plugin_name, "No acquisition")
            return
        if self._viewer is None:
            self.log_panel.log(f"[{plugin_name}] Viewer not ready.")
            return
        plugin = self.controller.registry.get(plugin_name)
        if plugin is None:
            self.log_panel.log(f"[{plugin_name}] Plugin not registered.")
            return

        selection = self.viewer_selection() or None  # None means all
        params_cls = plugin.parameters()
        params = (
            params_cls(**params_dict)
            if params_dict
            else plugin.default_params(
                self.controller.acquisition.optical
                if self.controller.acquisition
                else None
            )
        )
        ok = self._algorithm_runner.run(
            plugin=plugin,
            selection=selection,
            engine=self._viewer._engine,
            params=params,
        )
        if not ok:
            self.log_panel.log(f"[{plugin_name}] Wait for current run to finish.")
            self.processing_tabs.set_status(plugin_name, "Waiting: another run in progress")
        else:
            sel_text = f"{len(selection)} tiles" if selection else "all FOVs"
            self.log_panel.log(f"[{plugin_name}] Run started on {sel_text}.")
            self.processing_tabs.set_status(plugin_name, "Running...")

    def viewer_selection(self) -> set[int]:
        """Return the current selection (empty set if no viewer)."""
        if self._viewer is None:
            return set()
        return self._viewer.selection.selected

    def _on_run_progress(
        self, plugin_name: str, phase: str, current: int, total: int,
    ) -> None:
        self.processing_tabs.set_status(
            plugin_name, f"{phase}: {current}/{total}",
        )

    def _on_run_complete(self, plugin_name: str, tiles_processed: int) -> None:
        self.processing_tabs.mark_calibrated(plugin_name)
        self.processing_tabs.set_status(
            plugin_name, f"Applied to {tiles_processed} tiles",
        )
        self.log_panel.log(f"[{plugin_name}] Complete.")
        # Refresh viewer so position overrides / pipeline changes show
        if self._viewer is not None:
            self._viewer._canvas.clear()
            self._viewer._refresh()

    def _on_run_failed(self, plugin_name: str, error_message: str) -> None:
        self.processing_tabs.set_status(plugin_name, f"Failed: {error_message[:80]}")
        self.log_panel.log(f"[{plugin_name}] FAILED: {error_message}")
```

5. Remove the existing toggle-driven registration logic (we now go through `run_requested`). Specifically, in `_on_toggle_changed` (or similar), ensure it no longer auto-runs registration for the stitcher. The auto-run logic now lives in `ProcessingTabs._on_toggle`.

The existing `_rebuild_pipeline()` method stays (it wires the per-tile pipeline on toggle changes). The only change: toggling no longer directly runs the algorithm — that's the Run button's job now.

- [ ] **Step 2: Run full suite**

Run: `QT_QPA_PLATFORM=offscreen pytest -q`
Expected: All green.

- [ ] **Step 3: Commit**

```bash
git add squid_tools/gui/app.py
git commit -m "feat: MainWindow wires AlgorithmRunner to ProcessingTabs run_requested"
```

---

### Task 9: FlatfieldPlugin.run_live() — calibrate-then-apply

**Files:**
- Modify: `squid_tools/processing/flatfield/plugin.py`
- Create: `tests/unit/test_flatfield_run_live.py`

- [ ] **Step 1: Write failing test**

`tests/unit/test_flatfield_run_live.py`:
```python
"""Tests for FlatfieldPlugin.run_live()."""

from pathlib import Path

from squid_tools.processing.flatfield.plugin import FlatfieldPlugin, FlatfieldParams
from squid_tools.viewer.viewport_engine import ViewportEngine
from tests.fixtures.generate_fixtures import create_individual_acquisition


class TestFlatfieldRunLive:
    def test_run_live_emits_calibrate_phase(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = FlatfieldPlugin()
        params = FlatfieldParams()

        phases: list[str] = []
        def progress(phase, cur, total):
            phases.append(phase)

        plugin.run_live(
            selection={0, 1, 2, 3}, engine=engine,
            params=params, progress=progress,
        )
        assert any("Calibrat" in p for p in phases)
        assert any("Apply" in p for p in phases)

    def test_run_live_installs_pipeline(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = FlatfieldPlugin()
        params = FlatfieldParams()

        def progress(phase, cur, total): pass

        # Before run: pipeline empty
        assert len(engine._pipeline) == 0
        plugin.run_live(
            selection=None, engine=engine, params=params, progress=progress,
        )
        # After run: pipeline has one transform installed
        assert len(engine._pipeline) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_flatfield_run_live.py -v`
Expected: FAIL (phases list empty — current `run_live` is default)

- [ ] **Step 3: Implement FlatfieldPlugin.run_live()**

Add to `squid_tools/processing/flatfield/plugin.py`:

```python
    def run_live(self, selection, engine, params, progress):
        """Calibrate flatfield from samples, then install as per-tile transform."""
        import random

        # Phase 1: Calibrate
        candidates = selection if selection else engine.all_fov_indices()
        if not candidates:
            progress("Calibrating", 0, 1)
            progress("Applying", 1, 1)
            return

        n_samples = min(20, len(candidates))
        sample_indices = random.sample(sorted(candidates), n_samples)
        progress("Calibrating", 0, n_samples)

        tiles = []
        for i, fov in enumerate(sample_indices):
            tiles.append(
                engine.get_raw_frame(fov, z=0, channel=0, timepoint=0)
            )
            progress("Calibrating", i + 1, n_samples)

        # Compute flatfield via the existing correction code
        from squid_tools.processing.flatfield.correction import compute_flatfield
        flatfield = compute_flatfield(tiles)

        # Phase 2: Apply — install a per-tile transform into the engine pipeline
        progress("Applying", 0, 1)

        def _flatfield_transform(frame):
            from squid_tools.processing.flatfield.correction import apply_flatfield
            return apply_flatfield(frame, flatfield)

        # Merge with any existing transforms (keep others)
        existing = list(engine._pipeline)
        # Avoid duplicating: drop any previous flatfield transform tagged via attribute
        existing = [t for t in existing if not getattr(t, "_is_flatfield", False)]
        _flatfield_transform._is_flatfield = True  # type: ignore[attr-defined]
        existing.append(_flatfield_transform)
        engine.set_pipeline(existing)

        progress("Applying", 1, 1)
```

Note: `compute_flatfield` and `apply_flatfield` already exist in `flatfield/correction.py`. If the names differ in the actual code, the implementer should check and use the real API.

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_flatfield_run_live.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add squid_tools/processing/flatfield/plugin.py tests/unit/test_flatfield_run_live.py
git commit -m "feat: FlatfieldPlugin.run_live() — calibrate-from-samples + apply"
```

---

### Task 10: StitcherPlugin.run_live() — progressive pairwise

**Files:**
- Modify: `squid_tools/processing/stitching/plugin.py`
- Create: `tests/unit/test_stitcher_run_live.py`

- [ ] **Step 1: Write failing test**

`tests/unit/test_stitcher_run_live.py`:
```python
"""Tests for StitcherPlugin.run_live()."""

from pathlib import Path

from squid_tools.processing.stitching.plugin import StitcherPlugin, StitcherParams
from squid_tools.viewer.viewport_engine import ViewportEngine
from tests.fixtures.generate_fixtures import create_individual_acquisition


class TestStitcherRunLive:
    def test_run_live_emits_phases(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = StitcherPlugin()
        params = StitcherParams()

        phases: list[str] = []
        def progress(phase, cur, total):
            phases.append(phase)

        plugin.run_live(
            selection={0, 1, 2, 3}, engine=engine,
            params=params, progress=progress,
        )
        # Expect at least "Finding pairs" and "Registering" phases
        assert any("Finding pairs" in p for p in phases)
        # Registration phase emits per-pair progress
        assert any("Registering" in p or "Optimizing" in p for p in phases)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_stitcher_run_live.py -v`
Expected: FAIL (phases from default not matching).

- [ ] **Step 3: Implement StitcherPlugin.run_live()**

Add to `squid_tools/processing/stitching/plugin.py`:

```python
    def run_live(self, selection, engine, params, progress):
        """Progressive pairwise registration with live position updates."""
        from squid_tools.processing.stitching.registration import (
            find_adjacent_pairs,
            register_pair_worker,
        )
        from squid_tools.processing.stitching.optimization import (
            links_from_pairwise_metrics,
            two_round_optimization,
        )

        # Phase 1: Find pairs
        progress("Finding pairs", 0, 1)
        indices = selection if selection else engine.all_fov_indices()
        if len(indices) < 2:
            progress("Finding pairs", 1, 1)
            return

        nominal = engine.get_nominal_positions(indices)
        pixel_size = engine.pixel_size_um
        sorted_ids = sorted(nominal.keys())
        positions_px = [
            (nominal[i][1] * 1000.0 / pixel_size, nominal[i][0] * 1000.0 / pixel_size)
            for i in sorted_ids
        ]
        # Pick any loaded frame to determine tile shape
        sample_frame = engine.get_raw_frame(sorted_ids[0], z=0, channel=0, timepoint=0)
        tile_shape = sample_frame.shape[:2]
        pairs = find_adjacent_pairs(
            positions_px, (1.0, 1.0), tile_shape, min_overlap=15,
        )
        progress("Finding pairs", 1, 1)
        if not pairs:
            return

        # Phase 2: Register progressively
        total = len(pairs)
        pairwise_metrics: dict[tuple[int, int], tuple[int, int, float]] = {}

        for k, (i_pos, j_pos, _dy, _dx, _ov_y, _ov_x) in enumerate(pairs):
            progress("Registering", k, total)
            frame_i = engine.get_raw_frame(
                sorted_ids[i_pos], z=0, channel=0, timepoint=0,
            ).astype("float32")
            frame_j = engine.get_raw_frame(
                sorted_ids[j_pos], z=0, channel=0, timepoint=0,
            ).astype("float32")
            df = (params.downsample_factor, params.downsample_factor)
            result = register_pair_worker((
                i_pos, j_pos, frame_i, frame_j, df,
                params.ssim_window, params.ssim_threshold,
                (params.max_shift_pixels, params.max_shift_pixels),
            ))
            _, _, dy_s, dx_s, score = result
            if dy_s is not None:
                nom_dy = positions_px[j_pos][0] - positions_px[i_pos][0]
                nom_dx = positions_px[j_pos][1] - positions_px[i_pos][1]
                pairwise_metrics[(i_pos, j_pos)] = (
                    int(nom_dy + dy_s), int(nom_dx + dx_s), score,
                )
        progress("Registering", total, total)

        if not pairwise_metrics:
            return

        # Phase 3: Optimize & publish positions
        progress("Optimizing", 0, 1)
        links = links_from_pairwise_metrics(pairwise_metrics)
        shifts = two_round_optimization(
            links,
            n_tiles=len(sorted_ids),
            fixed_indices=[0],
            rel_thresh=3.0, abs_thresh=50.0, iterative=False,
        )
        overrides: dict[int, tuple[float, float]] = {}
        for i, idx in enumerate(sorted_ids):
            ox, oy = nominal[idx]
            overrides[idx] = (
                ox + float(shifts[i, 1]) * pixel_size / 1000.0,
                oy + float(shifts[i, 0]) * pixel_size / 1000.0,
            )
        engine.set_position_overrides(overrides)
        progress("Optimizing", 1, 1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_stitcher_run_live.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add squid_tools/processing/stitching/plugin.py tests/unit/test_stitcher_run_live.py
git commit -m "feat: StitcherPlugin.run_live() — progressive pairwise registration + global optimization"
```

---

### Task 11: Final verification

- [ ] **Step 1: Run full test suite**

Run: `QT_QPA_PLATFORM=offscreen pytest -q`
Expected: All tests pass. Total count should be ~235-240 (was 223, adding ~15 new tests).

- [ ] **Step 2: Run ruff**

Run: `ruff check squid_tools/ tests/`
Expected: All checks passed.

- [ ] **Step 3: Verify CLI still launches**

Run: `QT_QPA_PLATFORM=offscreen python -m squid_tools --version`
Expected: `squid-tools 0.1.0`

- [ ] **Step 4: Manual smoke test (skip if no display)**

On a machine with a display:
```
python -m squid_tools ~/Downloads/10x_mouse_brain_2025-04-23_00-53-11.236590
```

Verify:
- Shift+drag selects tiles (blue borders appear)
- Normal drag pans (no selection change)
- Processing tabs show toggle + Run button + status line
- Clicking Run for Flatfield shows "Calibrating..." then "Applied to N tiles"
- Clicking Run for Stitcher shows "Finding pairs..." then "Registering k/total..." progressing

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "chore: Cycle A final verification"
```
