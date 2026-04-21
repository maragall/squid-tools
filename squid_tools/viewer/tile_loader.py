"""Async tile loader: runs ViewportEngine.get_composite_tiles on a worker thread."""

from __future__ import annotations

import logging
import weakref
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, QThread, Signal

if TYPE_CHECKING:
    from squid_tools.viewer.viewport_engine import ViewportEngine

logger = logging.getLogger(__name__)

# Weak registry of live loaders so tests (and app shutdown) can stop
# every outstanding worker thread without relying on widget closeEvent
# propagating through Qt's C++ destruction cascade.
_active_loaders: weakref.WeakSet[AsyncTileLoader] = weakref.WeakSet()


def stop_all_loaders() -> None:
    """Stop every live AsyncTileLoader. Used by test teardown and app exit."""
    for loader in list(_active_loaders):
        try:
            loader.stop()
        except Exception:
            logger.exception("error stopping tile loader")


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

    def __init__(self, engine: ViewportEngine) -> None:
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
        self.tiles_ready.emit(req.request_id, tiles)
        if (
            self._pending is not None
            and self._pending.request_id > req.request_id
        ):
            self._process()


class AsyncTileLoader(QObject):
    """Public API: request tiles, receive tiles_ready on the GUI thread.

    `async_mode=True` (default) runs requests on a background QThread.
    `async_mode=False` runs synchronously on the caller thread; used by
    tests where Qt thread lifecycle vs. pytest GC is fragile.
    """

    # Process-wide default for async behavior. Test conftest sets this
    # to False; production leaves it True.
    _async_default: bool = True

    tiles_ready = Signal(int, object)
    request_failed = Signal(int, str)

    _submit_to_worker = Signal(object)

    def __init__(
        self,
        engine: ViewportEngine,
        parent: QObject | None = None,
        *,
        async_mode: bool | None = None,
    ) -> None:
        super().__init__(parent)
        self._next_id = 0
        self._stopped = False
        self._engine = engine
        self._async_mode = (
            async_mode if async_mode is not None
            else AsyncTileLoader._async_default
        )
        if self._async_mode:
            self._thread: QThread | None = QThread()
            self._thread.setObjectName("tile-loader")
            self._worker: _Worker | None = _Worker(engine)
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
        else:
            self._thread = None
            self._worker = None
        _active_loaders.add(self)

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
        if self._async_mode:
            self._submit_to_worker.emit(req)
        else:
            self._run_sync(req)
        return self._next_id

    def _run_sync(self, req: TileRequest) -> None:
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
            logger.exception("sync tile load failed")
            self.request_failed.emit(req.request_id, str(exc))
            return
        self.tiles_ready.emit(req.request_id, tiles)

    def stop(self) -> None:
        """Quit the worker thread. Safe to call multiple times."""
        if self._stopped:
            return
        self._stopped = True
        if self._thread is not None:
            try:
                self._thread.quit()
                self._thread.wait(2000)
            except RuntimeError:
                # C++ QThread object already deleted — nothing to do.
                pass
        _active_loaders.discard(self)
