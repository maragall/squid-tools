"""Background thread runner for ProcessingPlugin.run_live().

Runs plugin live execution in a QThread. Marshals progress
signals back to the GUI thread via Qt.
"""

from __future__ import annotations

import logging
import traceback
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

from pydantic import BaseModel
from PySide6.QtCore import QObject, QThread, Signal

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
        plugin: ProcessingPlugin,
        selection: set[int] | None,
        engine: ViewportEngine,
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
        plugin: ProcessingPlugin,
        selection: set[int] | None,
        engine: ViewportEngine,
        params: BaseModel,
    ) -> bool:
        """Start a plugin run. Returns True if accepted, False if another is in flight."""
        if self.is_running():
            return False
        logger.info("Starting plugin run: %s", plugin.name)
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
        logger.info(
            "Plugin run complete: %s (%d tiles)", plugin_name, tiles_processed,
        )
        self.run_complete.emit(plugin_name, tiles_processed)
        self._cleanup()

    def _on_failed(self, plugin_name: str, error_message: str) -> None:
        logger.error(
            "Plugin run failed: %s — %s",
            plugin_name, error_message.splitlines()[0],
        )
        self.run_failed.emit(plugin_name, error_message)
        self._cleanup()

    def _cleanup(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
            self._worker = None
