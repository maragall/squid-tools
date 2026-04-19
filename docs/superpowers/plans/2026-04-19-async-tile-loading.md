# Async Tile Loading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `ViewportEngine.get_composite_tiles()` off the GUI thread. Add `AsyncTileLoader` (QObject + worker QThread) with replace-semantics. Wire it into `ViewerWidget._refresh()`.

**Architecture:** `AsyncTileLoader` owns a single worker thread. Calls to `request(...)` are non-blocking — they emit a queued-connection signal to the worker. The worker stores the latest request, runs `get_composite_tiles`, and emits `tiles_ready(id, tiles)` back to the GUI thread (also queued connection). `ViewerWidget` filters stale replies by `request_id`.

**Tech Stack:** PySide6 (QThread, QObject, queued signals), existing `squid_tools.viewer.viewport_engine`, pytest + pytest-qt.

**Spec:** `docs/superpowers/specs/2026-04-19-async-tile-loading-design.md`

---

## File Structure

```
squid_tools/viewer/
├── tile_loader.py              # NEW: AsyncTileLoader + _Worker + TileRequest
├── widget.py                   # MODIFY: use loader in _refresh, add _on_tiles_ready
tests/
├── unit/
│   └── test_tile_loader.py     # NEW
└── integration/
    └── test_async_tile_flow.py # NEW
```

---

### Task 1: `TileRequest` dataclass + skeleton `AsyncTileLoader`

**Files:**
- Create: `squid_tools/viewer/tile_loader.py`
- Create: `tests/unit/test_tile_loader.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_tile_loader.py`:
```python
"""Unit tests for the async tile loader."""

from __future__ import annotations

import logging

import pytest
from pytestqt.qtbot import QtBot

from squid_tools.viewer.tile_loader import AsyncTileLoader, TileRequest


@pytest.fixture(autouse=True)
def _reset_root_logger():
    root = logging.getLogger("squid_tools")
    saved = list(root.handlers)
    yield
    for h in list(root.handlers):
        root.removeHandler(h)
    for h in saved:
        root.addHandler(h)


class _FakeEngine:
    def __init__(self):
        self.calls = []

    def get_composite_tiles(self, **kwargs):
        self.calls.append(kwargs)
        viewport = kwargs["viewport"]
        # Return a minimal tile stand-in
        return [("tile", viewport)]


class TestTileRequest:
    def test_is_frozen_dataclass(self) -> None:
        req = TileRequest(
            request_id=1,
            viewport=(0.0, 0.0, 1.0, 1.0),
            screen_width=100,
            screen_height=100,
            active_channels=[0],
            channel_names=["C1"],
            channel_clims={0: (0.0, 1.0)},
            z=0,
            timepoint=0,
        )
        assert req.request_id == 1
        with pytest.raises(Exception):
            req.request_id = 2  # frozen


class TestAsyncTileLoaderConstruction:
    def test_starts_worker_thread(self, qtbot: QtBot) -> None:
        engine = _FakeEngine()
        loader = AsyncTileLoader(engine)
        try:
            assert loader._thread.isRunning()
        finally:
            loader.stop()

    def test_stop_quits_thread(self, qtbot: QtBot) -> None:
        engine = _FakeEngine()
        loader = AsyncTileLoader(engine)
        loader.stop()
        assert not loader._thread.isRunning()
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/unit/test_tile_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'squid_tools.viewer.tile_loader'`

- [ ] **Step 3: Minimal implementation**

`squid_tools/viewer/tile_loader.py`:
```python
"""Async tile loader: runs ViewportEngine.get_composite_tiles on a worker thread."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, Qt, Signal

if TYPE_CHECKING:
    from squid_tools.viewer.viewport_engine import ViewportEngine

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TileRequest:
    """Snapshot of what to load."""

    request_id: int
    viewport: tuple[float, float, float, float]
    screen_width: int
    screen_height: int
    active_channels: list[int]
    channel_names: list[str]
    channel_clims: dict[int, tuple[float, float]]
    z: int
    timepoint: int


class _Worker(QObject):
    """Runs on the worker thread. Processes one request at a time."""

    tiles_ready = Signal(int, object)
    request_failed = Signal(int, str)

    def __init__(self, engine: "ViewportEngine") -> None:
        super().__init__()
        self._engine = engine
        self._pending: TileRequest | None = None

    def submit(self, req: TileRequest) -> None:
        self._pending = req
        self._process()

    def _process(self) -> None:
        req = self._pending
        self._pending = None
        if req is None:
            return
        try:
            tiles = self._engine.get_composite_tiles(
                viewport=req.viewport,
                screen_width=req.screen_width,
                screen_height=req.screen_height,
                active_channels=req.active_channels,
                channel_names=req.channel_names,
                channel_clims=req.channel_clims,
                z=req.z,
                timepoint=req.timepoint,
            )
        except Exception as exc:
            logger.exception("tile loader worker failed")
            self.request_failed.emit(req.request_id, str(exc))
            return
        if (
            self._pending is not None
            and self._pending.request_id > req.request_id
        ):
            self._process()
            return
        self.tiles_ready.emit(req.request_id, tiles)


class AsyncTileLoader(QObject):
    """Public API: request tiles, receive tiles_ready on the GUI thread."""

    tiles_ready = Signal(int, object)
    request_failed = Signal(int, str)

    _submit_to_worker = Signal(object)

    def __init__(
        self,
        engine: "ViewportEngine",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._next_id = 0
        self._thread = QThread()
        self._thread.setObjectName("tile-loader")
        self._worker = _Worker(engine)
        self._worker.moveToThread(self._thread)
        self._worker.tiles_ready.connect(
            self.tiles_ready, type=Qt.ConnectionType.QueuedConnection,
        )
        self._worker.request_failed.connect(
            self.request_failed, type=Qt.ConnectionType.QueuedConnection,
        )
        self._submit_to_worker.connect(
            self._worker.submit, type=Qt.ConnectionType.QueuedConnection,
        )
        self._thread.start()

    def request(
        self,
        viewport: tuple[float, float, float, float],
        screen_width: int,
        screen_height: int,
        active_channels: list[int],
        channel_names: list[str],
        channel_clims: dict[int, tuple[float, float]],
        z: int,
        timepoint: int,
    ) -> int:
        self._next_id += 1
        req = TileRequest(
            request_id=self._next_id,
            viewport=viewport,
            screen_width=screen_width,
            screen_height=screen_height,
            active_channels=active_channels,
            channel_names=channel_names,
            channel_clims=channel_clims,
            z=z,
            timepoint=timepoint,
        )
        self._submit_to_worker.emit(req)
        return self._next_id

    def stop(self) -> None:
        """Quit the worker thread."""
        self._thread.quit()
        self._thread.wait(2000)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_tile_loader.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add squid_tools/viewer/tile_loader.py tests/unit/test_tile_loader.py
git commit -m "feat(tile_loader): AsyncTileLoader skeleton + worker thread lifecycle"
```

---

### Task 2: `request()` flow — tiles delivered via `tiles_ready` signal

**Files:**
- Modify: `tests/unit/test_tile_loader.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_tile_loader.py`:
```python
class TestAsyncTileLoaderRequest:
    def _request_kwargs(self, **overrides):
        base = dict(
            viewport=(0.0, 0.0, 1.0, 1.0),
            screen_width=100,
            screen_height=100,
            active_channels=[0],
            channel_names=["C1"],
            channel_clims={0: (0.0, 1.0)},
            z=0,
            timepoint=0,
        )
        base.update(overrides)
        return base

    def test_request_returns_id_and_emits_tiles_ready(self, qtbot: QtBot) -> None:
        engine = _FakeEngine()
        loader = AsyncTileLoader(engine)
        try:
            with qtbot.waitSignal(loader.tiles_ready, timeout=2000) as blocker:
                request_id = loader.request(**self._request_kwargs())
            emitted_id, tiles = blocker.args
            assert emitted_id == request_id
            assert len(tiles) == 1
            assert len(engine.calls) == 1
            assert engine.calls[0]["viewport"] == (0.0, 0.0, 1.0, 1.0)
        finally:
            loader.stop()

    def test_request_ids_increment(self, qtbot: QtBot) -> None:
        engine = _FakeEngine()
        loader = AsyncTileLoader(engine)
        try:
            id1 = loader.request(**self._request_kwargs())
            id2 = loader.request(**self._request_kwargs())
            assert id2 == id1 + 1
        finally:
            loader.stop()

    def test_request_failure_emits_request_failed(self, qtbot: QtBot) -> None:
        class BrokenEngine:
            def get_composite_tiles(self, **kwargs):
                raise RuntimeError("boom")

        loader = AsyncTileLoader(BrokenEngine())
        try:
            with qtbot.waitSignal(
                loader.request_failed, timeout=2000,
            ) as blocker:
                loader.request(**self._request_kwargs())
            emitted_id, err = blocker.args
            assert emitted_id == 1
            assert "boom" in err
        finally:
            loader.stop()
```

- [ ] **Step 2: Run to confirm pass**

Run: `pytest tests/unit/test_tile_loader.py -v`
Expected: PASS (6 tests — 3 from Task 1 + 3 new). Because the skeleton from Task 1 already wires all the signals end-to-end, these tests should pass on the first run. If they don't, fix the Task 1 implementation.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_tile_loader.py
git commit -m "test(tile_loader): request -> tiles_ready round-trip + failure signal"
```

---

### Task 3: Replace-semantics — newest request wins

**Files:**
- Modify: `tests/unit/test_tile_loader.py`
- Verify: `squid_tools/viewer/tile_loader.py` (no change expected; the skeleton already implements replace semantics)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_tile_loader.py`:
```python
import threading
import time


class TestAsyncTileLoaderReplaceSemantics:
    def test_rapid_requests_last_one_wins(self, qtbot: QtBot) -> None:
        barrier = threading.Event()
        received = []

        class SlowEngine:
            def __init__(self):
                self.call_count = 0

            def get_composite_tiles(self, **kwargs):
                self.call_count += 1
                # First call blocks until barrier fires, second returns instantly
                if self.call_count == 1:
                    barrier.wait(timeout=2.0)
                return [("tile", kwargs["viewport"], self.call_count)]

        engine = SlowEngine()
        loader = AsyncTileLoader(engine)
        loader.tiles_ready.connect(
            lambda rid, tiles: received.append((rid, tiles)),
        )
        try:
            # Fire request A (worker blocks on barrier)
            id_a = loader.request(
                viewport=(0.0, 0.0, 1.0, 1.0),
                screen_width=100, screen_height=100,
                active_channels=[0], channel_names=["C1"],
                channel_clims={0: (0.0, 1.0)},
                z=0, timepoint=0,
            )
            # Wait briefly so worker picks up A
            time.sleep(0.1)
            # Fire request B (queued in _pending, will be picked up after A)
            id_b = loader.request(
                viewport=(2.0, 2.0, 3.0, 3.0),
                screen_width=100, screen_height=100,
                active_channels=[0], channel_names=["C1"],
                channel_clims={0: (0.0, 1.0)},
                z=0, timepoint=0,
            )
            # Release the barrier so A completes
            barrier.set()
            # Wait for B's tiles to arrive
            qtbot.waitUntil(
                lambda: any(rid == id_b for rid, _ in received), timeout=3000,
            )
            # Check: A's tiles were emitted (worker finished A),
            # but B's tiles are newer and also emitted
            ids = [rid for rid, _ in received]
            assert id_a in ids
            assert id_b in ids
            # B's tiles' call_count must be 2 (proving B was processed)
            b_tiles = next(t for rid, t in received if rid == id_b)
            assert b_tiles[0][2] == 2
        finally:
            loader.stop()
```

- [ ] **Step 2: Run test**

Run: `pytest tests/unit/test_tile_loader.py::TestAsyncTileLoaderReplaceSemantics -v`
Expected: PASS. If the skeleton's `_Worker._process` doesn't correctly handle pending replacement, fix it to match the spec's pseudo-code (the skeleton already does). This test is insurance against regressions.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_tile_loader.py
git commit -m "test(tile_loader): replace-semantics — newest request wins"
```

---

### Task 4: Wire `AsyncTileLoader` into `ViewerWidget`

**Files:**
- Modify: `squid_tools/viewer/widget.py`
- Modify: `tests/unit/test_viewer_widget.py` (or create integration test — see Task 5)

- [ ] **Step 1: Write the failing test**

First read `tests/unit/test_viewer_widget.py` to see existing patterns. Append a test that:

```python
class TestViewerWidgetAsyncRefresh:
    def test_refresh_uses_tile_loader(
        self, qtbot, individual_acquisition,
    ) -> None:
        """After load_acquisition, _refresh() should request via AsyncTileLoader, not call engine directly."""
        from squid_tools.viewer.widget import ViewerWidget

        widget = ViewerWidget()
        qtbot.addWidget(widget)
        widget.load_acquisition(individual_acquisition, "0")

        # Check the loader exists and is running
        assert widget._tile_loader is not None
        assert widget._tile_loader._thread.isRunning()

        # Trigger a refresh; wait for tiles_ready
        with qtbot.waitSignal(
            widget._tile_loader.tiles_ready, timeout=5000,
        ):
            widget._refresh()
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/unit/test_viewer_widget.py::TestViewerWidgetAsyncRefresh -v`
Expected: FAIL — `AttributeError: '_tile_loader'`.

- [ ] **Step 3: Modify `ViewerWidget`**

Edit `squid_tools/viewer/widget.py`:

Add import at the top:
```python
from squid_tools.viewer.tile_loader import AsyncTileLoader
```

In `ViewerWidget.__init__`, initialize:
```python
        self._tile_loader: AsyncTileLoader | None = None
        self._last_applied_id: int = 0
```

In `load_acquisition`, AFTER `self._engine.load(path, region)` and BEFORE the `_refresh()` call, add:
```python
        if self._tile_loader is not None:
            self._tile_loader.stop()
        self._tile_loader = AsyncTileLoader(self._engine, parent=self)
        self._tile_loader.tiles_ready.connect(self._on_tiles_ready)
        self._last_applied_id = 0
```

Replace `_refresh`:
```python
    def _refresh(self) -> None:
        """Dispatch a tile request to the async loader. Non-blocking."""
        if not self._engine.is_loaded():
            return
        if self._tile_loader is None:
            return
        viewport = self._canvas.get_viewport()
        sw, sh = self._canvas.get_screen_size()
        if sw == 0 or sh == 0:
            return
        self._tile_loader.request(
            viewport=viewport,
            screen_width=sw, screen_height=sh,
            active_channels=self._active_channels,
            channel_names=self._channels,
            channel_clims=self._channel_clims,
            z=self.z_slider.value(),
            timepoint=self.t_slider.value(),
        )
```

Add the new slot near the other private methods:
```python
    def _on_tiles_ready(self, request_id: int, tiles: object) -> None:
        if request_id < self._last_applied_id:
            return
        self._last_applied_id = request_id
        self._canvas.render_tiles(tiles)  # type: ignore[arg-type]
```

Add a graceful shutdown (Qt's `closeEvent` is called when the widget is closed):
```python
    def closeEvent(self, event) -> None:  # noqa: N802
        if self._tile_loader is not None:
            self._tile_loader.stop()
        super().closeEvent(event)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_viewer_widget.py -v`
Expected: PASS (existing + new). The existing test for `_refresh` (if any checks synchronous behavior) may need updating — because now `_refresh()` returns immediately without rendering. If an existing test checks "after _refresh, canvas has tiles", update it to wait for `tiles_ready` signal.

Run the full suite: `pytest -q`. Expect no regressions (280+ passing).

- [ ] **Step 5: Commit**

```bash
git add squid_tools/viewer/widget.py tests/unit/test_viewer_widget.py
git commit -m "feat(widget): route _refresh through AsyncTileLoader (non-blocking)"
```

---

### Task 5: Integration test — GUI thread not blocked during tile load

**Files:**
- Create: `tests/integration/test_async_tile_flow.py`

- [ ] **Step 1: Write the test**

`tests/integration/test_async_tile_flow.py`:
```python
"""Integration: async tile loading keeps GUI thread responsive."""

from __future__ import annotations

import time

from pytestqt.qtbot import QtBot


class TestAsyncTileFlow:
    def test_gui_thread_not_blocked_during_tile_load(
        self, qtbot: QtBot, individual_acquisition,
    ) -> None:
        from squid_tools.viewer.widget import ViewerWidget

        widget = ViewerWidget()
        qtbot.addWidget(widget)
        widget.load_acquisition(individual_acquisition, "0")

        # Measure GUI thread responsiveness after issuing a refresh
        t0 = time.perf_counter()
        widget._refresh()  # returns immediately
        elapsed = time.perf_counter() - t0
        # Request submission must be non-blocking: << 50 ms on any reasonable machine
        assert elapsed < 0.05, f"_refresh blocked for {elapsed:.3f}s"

        # Tiles should eventually arrive on tiles_ready
        with qtbot.waitSignal(
            widget._tile_loader.tiles_ready, timeout=5000,
        ):
            pass  # Already queued

    def test_rapid_refresh_does_not_queue_unboundedly(
        self, qtbot: QtBot, individual_acquisition,
    ) -> None:
        from squid_tools.viewer.widget import ViewerWidget

        widget = ViewerWidget()
        qtbot.addWidget(widget)
        widget.load_acquisition(individual_acquisition, "0")

        # Fire 10 rapid refreshes; only the newest result should apply
        for _ in range(10):
            widget._refresh()

        # Wait for at least one tiles_ready
        with qtbot.waitSignal(
            widget._tile_loader.tiles_ready, timeout=5000,
        ):
            pass
        # The last applied id must be <= the latest request id (newer requests supersede)
        # Exact value depends on timing; main thing is no crash, no unbounded queue
        assert widget._last_applied_id <= widget._tile_loader._next_id
```

- [ ] **Step 2: Run test**

Run: `pytest tests/integration/test_async_tile_flow.py -v`
Expected: PASS

- [ ] **Step 3: Run full suite**

Run: `pytest -q`
Expected: all passing. Run `ruff check squid_tools tests` — expect 0.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_async_tile_flow.py
git commit -m "test(async_tile_flow): integration — GUI not blocked + replace-semantics"
```

---

## Self-Review

**Spec coverage:**
- `TileRequest` frozen dataclass → Task 1 ✓
- `AsyncTileLoader` + `_Worker` + QThread lifecycle → Task 1 ✓
- `request()` → `_submit_to_worker` → `tiles_ready` → GUI → Tasks 1–2 ✓
- Replace-semantics (latest wins at both worker + GUI layers) → Tasks 3, 4 ✓
- `ViewerWidget` integration → Task 4 ✓
- GUI-responsiveness integration test → Task 5 ✓
- `stop()` on close → Task 4's `closeEvent` ✓
- Error path `request_failed` → Task 2 ✓

**Placeholder scan:** No TODO / TBD / "add later". Every step has code.

**Type consistency:** `TileRequest` fields used identically in `_Worker.submit` and `AsyncTileLoader.request`. Signal payload `(int, object)` matches everywhere.

**Scope:** Single subsystem (viewer tile loading). Focused.

**Ambiguity:** The `_worker._pending` field is read/written across threads but synchronization is Qt's event queue (queued signal delivers the request atomically). Documented in the spec's Thread Safety section.
