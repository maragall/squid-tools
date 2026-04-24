# Async Tile Loading Design Spec

## Purpose

Move tile loading off the GUI thread. Today, every pan/zoom blocks the GUI until `ViewportEngine.get_composite_tiles()` finishes its disk reads and compositing. For large mosaics or remote storage, this stall is visible and makes the viewer feel sluggish. This cycle adds a dedicated worker thread that loads and composites tiles while the GUI thread stays responsive — the last rendered frame stays on screen (like Google Maps), and the new tiles arrive when ready.

**Audience:** End users (smoother panning, especially over 8+ channels or large mosaics) and future cycles (3D volume rendering needs this pipeline to avoid stalling frustrum updates).

**Guiding principle:** The GUI thread never blocks on IO. Requests can be replaced mid-flight. The newest viewport always wins.

---

## Scope

**IN:**
- `squid_tools/viewer/tile_loader.py` with `AsyncTileLoader(QObject)` owning a `QThread` and a `_Worker(QObject)`
- Replace-semantics request model: submitting a new request supersedes any pending/in-flight request; only the latest result is delivered to the GUI
- Signal `tiles_ready(viewport_id: int, tiles: list)` — GUI slot matches by `viewport_id` and ignores stale replies
- `ViewerWidget._refresh()` becomes non-blocking: asks the loader to fetch, returns immediately; GUI paints whatever it already has
- GUI thread still calls `_canvas.render_tiles()` when `tiles_ready` fires
- Graceful shutdown: `AsyncTileLoader.stop()` quits the thread on app close; `ViewerWidget` calls `stop()` on teardown
- Tests: unit tests for the loader (mocked engine); integration test that pans the viewer and confirms the GUI thread never blocks > 50 ms

**OUT (future cycles):**
- Prefetching (loading tiles outside the viewport speculatively)
- Multiple worker threads (one is enough for disk-bound loads)
- Priority queues for viewport regions (closest tiles first)
- Cancelling mid-tile reads (we cancel at the request boundary; a tile already being read completes then we discard)
- GPU compositing (Cycle F handles that)
- 3D frustrum (Cycle E handles that)

---

## Architecture

```
User pans / zooms
  -> StageCanvas emits draw event
  -> ViewerWidget._refresh_timer debounces 50 ms
  -> ViewerWidget._refresh():
       params = build params from viewport + sliders + channel state
       self._tile_loader.request(params)          # NON-BLOCKING
  (GUI thread free to pan more, render last frame)

AsyncTileLoader:
  - owns _thread: QThread
  - owns _worker: _Worker (lives on _thread)
  - _pending: the most recent request (overwritten on each request())
  - signal _request_ready emitted to wake worker

_Worker (runs on _thread):
  - loop: on _request_ready, read _pending atomically, clear it
  - call engine.get_composite_tiles(...) with request params
  - emit tiles_ready(request_id, tiles) back to GUI thread

ViewerWidget._on_tiles_ready(request_id, tiles):
  if request_id < self._last_applied_id: return   # stale
  self._canvas.render_tiles(tiles)
  self._last_applied_id = request_id
```

Qt's default AutoConnection + QThread + moveToThread() gives us Qt.QueuedConnection across thread boundaries automatically. Signals marshal the `tiles` list through Qt's event loop; the GUI thread picks them up on its next tick.

---

## Components

### 1. `squid_tools/viewer/tile_loader.py`

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

    tiles_ready = Signal(int, object)  # request_id, list-of-tiles
    request_failed = Signal(int, str)  # request_id, error

    def __init__(self, engine: ViewportEngine) -> None:
        super().__init__()
        self._engine = engine
        self._pending: TileRequest | None = None

    def submit(self, req: TileRequest) -> None:
        """Replace the pending request. Called from the worker thread
        via a Qt.QueuedConnection signal from AsyncTileLoader."""
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
        # If a newer request arrived while we were working, skip delivery
        # and process that one instead.
        if self._pending is not None and self._pending.request_id > req.request_id:
            self._process()
            return
        self.tiles_ready.emit(req.request_id, tiles)


class AsyncTileLoader(QObject):
    """Public API: request tiles, get tiles_ready signal back on the GUI thread."""

    tiles_ready = Signal(int, object)  # request_id, tiles (mirrors worker)
    request_failed = Signal(int, str)

    _submit_to_worker = Signal(object)  # TileRequest — marshalled across threads

    def __init__(
        self, engine: ViewportEngine, parent: QObject | None = None,
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
        """Submit a request. Returns the request_id."""
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
        """Quit the worker thread. Must be called before the loader is destroyed."""
        self._thread.quit()
        self._thread.wait(2000)
```

### 2. `squid_tools/viewer/widget.py` changes

- In `load_acquisition`, after `self._engine.load(...)`, construct the loader:
  ```python
  self._tile_loader = AsyncTileLoader(self._engine, parent=self)
  self._tile_loader.tiles_ready.connect(self._on_tiles_ready)
  self._last_applied_id = 0
  ```
- `_refresh()` becomes:
  ```python
  def _refresh(self) -> None:
      if not self._engine.is_loaded():
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
- New slot `_on_tiles_ready(request_id, tiles)` filters stale replies and calls `_canvas.render_tiles`.
- On widget destroy / close, call `self._tile_loader.stop()`.

---

## Data Flow

1. User pans → canvas draw event → 50 ms debounce timer
2. `_refresh()` calls `self._tile_loader.request(...)` — returns immediately with a request_id
3. Loader emits `_submit_to_worker` → QueuedConnection to `_Worker.submit` on worker thread
4. Worker replaces `_pending`, calls `engine.get_composite_tiles(...)`
5. Worker checks: is `_pending` now a NEWER request? If yes, loop to process it first
6. Worker emits `tiles_ready(id, tiles)` — QueuedConnection back to GUI
7. GUI slot filters: if `id < _last_applied_id`, ignore. Otherwise, render and update `_last_applied_id`

Stale request handling: older requests that were superseded are dropped both in the worker (`if pending.request_id > req.request_id`) and in the GUI slot. The newest-wins invariant is maintained on both sides.

---

## Thread Safety

- `ViewportEngine` internals touched by `get_composite_tiles`: `_reader.read_frame` (goes through the handle pool — already thread-safe), `_raw_cache` (thread-safe LRU), dask array slicing (thread-safe), numpy compositing (no shared state).
- State MUTATIONS on the engine (`set_pipeline`, `set_position_overrides`, `_index` rebuild) happen on the GUI thread during `load_acquisition` or plugin runs. These must NOT happen while a tile request is in flight. Current call sites (`widget._on_slider_changed`, `app._rebuild_pipeline`, `algorithm_runner._on_complete`) all trigger a new `_refresh()` after mutation — so the old tiles that come back are filtered out by `_last_applied_id`, and the new request sees the new state.
- The `_worker._pending` field is written from the main thread via `_submit_to_worker` (queued connection, atomic in Qt's event loop) and read from the worker thread. Qt's queued connection acts as the synchronization point — when the worker processes a queued signal, it has a happens-before with the main-thread emit.

---

## Error Handling

| Failure | Behavior |
|---------|----------|
| Worker raises during `get_composite_tiles` | `request_failed(id, str)` signal; viewer logs ERROR, keeps last frame on screen |
| Thread can't start | `AsyncTileLoader.__init__` catches and falls back to synchronous mode (calls `get_composite_tiles` directly in `request`). Logs a WARNING. |
| Stop timeout (2 s) exceeded | Logs WARNING; thread is detached. App still closes. |
| Request arrives during shutdown | Ignored (worker will see quit event before processing). |

---

## UX Details

No visible UI change. The improvement is perceptual:

- **Today:** panning over a 50-FOV mosaic with 4 channels: each drag step stalls 100–300 ms while disk reads complete. The pan feels stuttery.
- **After:** the same pan animates smoothly. The last-drawn frame stays visible while the new one loads; when it arrives, it replaces the old one. If the user pans past the first target viewport, the first request is silently discarded.

Log output (at DEBUG):
```
[14:23:15] [DEBUG] [viewer] tile request id=42 viewport=(10,8,25,20)
[14:23:15] [DEBUG] [viewer] tile request id=43 viewport=(12,10,27,22)
[14:23:15] [DEBUG] [viewer] tile request id=42 superseded by 43 (dropped)
[14:23:15] [DEBUG] [viewer] tiles ready id=43 (18 tiles)
```

---

## Follow-ups from Cycle B not addressed here

None. This cycle touches `viewer/` only; it does not depend on logger deviations.

---

## Testing Plan

**(Written at end of all cycles — functional user workflow tests for the complete integrated product. Per-cycle TDD is handled by superpowers during implementation.)**

Placeholder: this cycle's TDD tests live in its implementation plan. The spec's Testing Plan section will be written when all planned cycles are complete, describing end-to-end user workflows to validate the full product.
