"""Bottom log panel: status bar + scrollable log console.

Status bar: real-time heap RSS, cache occupancy, GPU info.
Console: scrollable text log showing every action, error, and data flow event.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


def _get_rss_mb() -> float:
    """Get current process RSS in MB."""
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss_kb = usage.ru_maxrss
        if os.uname().sysname == "Darwin":
            return rss_kb / (1024 * 1024)
        return rss_kb / 1024
    except Exception:
        return 0.0


class QtLogHandler(QObject, logging.Handler):
    """Logging handler that emits a Qt signal per record.

    Must subclass QObject for signals. Multiple-inheritance with
    logging.Handler is fine because Handler is a pure-Python class.
    """

    record_emitted = Signal(str, int, str, str)
    # (timestamp_str HH:MM:SS, level_int, short_tag_str, message_str)

    def __init__(self) -> None:
        QObject.__init__(self)
        logging.Handler.__init__(self)

    def emit(self, record: logging.LogRecord) -> None:  # noqa: A003
        from squid_tools.logger import short_tag

        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        tag = short_tag(record.name)
        msg = record.getMessage()
        if record.exc_info:
            tb = logging.Formatter().formatException(record.exc_info)
            msg = f"{msg}\n{tb}"
        self.record_emitted.emit(ts, record.levelno, tag, msg)


class LogPanel(QWidget):
    """Status bar + scrollable log console."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scrollable console (collapsible)
        self._console = QPlainTextEdit()
        self._console.setReadOnly(True)
        self._console.setMaximumBlockCount(500)
        self._console.setStyleSheet(
            "QPlainTextEdit { background: #1a1a1a; color: #aaaaaa; "
            "font-family: monospace; font-size: 11px; border: none; }"
        )
        self._console.setFixedHeight(120)
        layout.addWidget(self._console)

        # Status bar row
        status_row = QHBoxLayout()
        status_row.setContentsMargins(4, 2, 4, 2)

        self._status_label = QLabel("Ready")
        self._cache_label = QLabel("Cache: --")
        self._memory_label = QLabel("Heap: --")
        self._gpu_label = QLabel("GPU: detecting...")

        self._console_level = logging.INFO
        self._level_filter = QComboBox()
        self._level_filter.addItems(["DEBUG", "INFO", "WARN", "ERROR"])
        self._level_filter.setCurrentText("INFO")
        self._level_filter.setToolTip(
            "Console log verbosity (file always captures DEBUG)"
        )
        self._level_filter.currentTextChanged.connect(self._on_level_changed)

        status_row.addWidget(self._status_label, stretch=2)
        status_row.addWidget(self._level_filter)
        status_row.addWidget(self._cache_label, stretch=2)
        status_row.addWidget(self._memory_label, stretch=1)
        status_row.addWidget(self._gpu_label, stretch=1)

        layout.addLayout(status_row)

        self._detect_gpu()

        # Memory polling
        self._data_manager = None
        self._mem_timer = QTimer(self)
        self._mem_timer.timeout.connect(self._update_memory)
        self._mem_timer.start(500)

        self._qt_handler = QtLogHandler()
        self._qt_handler.setLevel(logging.DEBUG)
        self._qt_handler.record_emitted.connect(self._on_log_record)
        _sq_logger = logging.getLogger("squid_tools")
        _sq_logger.setLevel(logging.DEBUG)
        _sq_logger.addHandler(self._qt_handler)

    def log(self, message: str) -> None:
        """Backwards-compat: route a plain string through Python logging at INFO."""
        logging.getLogger("squid_tools.gui").info(message)

    def _on_log_record(
        self, ts: str, level: int, tag: str, message: str,
    ) -> None:
        if level < self._console_level:
            return
        level_name = logging.getLevelName(level)
        self._console.appendPlainText(
            f"[{ts}] [{level_name}] [{tag}] {message}"
        )

    def _on_level_changed(self, text: str) -> None:
        mapping = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARN": logging.WARNING,
            "ERROR": logging.ERROR,
        }
        self._console_level = mapping.get(text, logging.INFO)

    def closeEvent(self, event: object) -> None:  # noqa: N802
        try:
            logging.getLogger("squid_tools").removeHandler(self._qt_handler)
        finally:
            super().closeEvent(event)  # type: ignore[arg-type]

    def text(self) -> str:
        """Return last log line."""
        return self._console.toPlainText().split("\n")[-1] if self._console.toPlainText() else ""

    def set_status(self, status: str) -> None:
        """Set the status label."""
        self._status_label.setText(status)

    def status_text(self) -> str:
        """Return current status text."""
        return self._status_label.text()

    def set_gpu_info(self, gpu_name: str) -> None:
        """Set GPU info label."""
        self._gpu_label.setText(f"GPU: {gpu_name}")

    def gpu_text(self) -> str:
        """Return current GPU text."""
        return self._gpu_label.text()

    def set_memory_info(self, used_gb: float, total_gb: float) -> None:
        """Set memory usage label."""
        self._memory_label.setText(f"Mem: {used_gb:.1f}/{total_gb:.0f} GB")

    def memory_text(self) -> str:
        """Return current memory text."""
        return self._memory_label.text()

    def set_data_manager(self, dm: object) -> None:
        """Connect to a ViewportDataManager for cache stats."""
        self._data_manager = dm

    def _update_memory(self) -> None:
        """Poll memory stats. Called by timer every 500ms."""
        rss = _get_rss_mb()
        self._memory_label.setText(f"Heap: {rss:.0f} MB")

        if self._data_manager is not None:
            try:
                cache = self._data_manager._raw_cache  # type: ignore[attr-defined]
                cache_mb = cache.current_bytes / (1024 * 1024)
                max_mb = cache._max_bytes / (1024 * 1024)
                thumb_count = len(self._data_manager._thumb_cache)  # type: ignore[attr-defined]
                self._cache_label.setText(
                    f"Cache: {cache_mb:.0f}/{max_mb:.0f} MB | Thumbs: {thumb_count}"
                )
            except Exception:
                pass

    def _detect_gpu(self) -> None:
        """Detect GPU at startup using core detection."""
        from squid_tools.core.gpu import detect_gpu

        info = detect_gpu()
        if info.available:
            self.set_gpu_info(info.name)
        else:
            self.set_gpu_info("CPU only")
