"""Async tile loader: runs ViewportEngine.get_composite_tiles on a worker thread."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, QThread, Signal

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
    """Public API: request tiles, receive tiles_ready on the GUI thread."""

    tiles_ready = Signal(int, object)
    request_failed = Signal(int, str)

    _submit_to_worker = Signal(object)

    def __init__(
        self,
        engine: ViewportEngine,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._next_id = 0
        self._stopped = False
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
        """Quit the worker thread. Safe to call multiple times."""
        if self._stopped:
            return
        self._stopped = True
        try:
            self._thread.quit()
            self._thread.wait(2000)
        except RuntimeError:
            # C++ QThread object already deleted — nothing to do.
            pass
