# Production Logger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ad-hoc `log_panel.log()` calls with Python's `logging` module. Route records to a rotating file (for post-mortem debugging) and the GUI log console (for live feedback). Legacy `log_panel.log()` keeps working via backwards-compat pass-through.

**Architecture:** A `squid_tools/logger.py` module configures the `squid_tools` root logger with a `RotatingFileHandler` (10 MB × 5). `LogPanel` attaches a `QtLogHandler` that emits Qt signals per record. A level-filter dropdown controls console verbosity (default INFO). The file always captures DEBUG+. Non-GUI modules get `logger = logging.getLogger(__name__)` and emit through the standard API; the GUI passes messages through the same pipe.

**Tech Stack:** Python `logging` + `logging.handlers.RotatingFileHandler`, PySide6 (QObject, Signal, QComboBox), pytest, pytest-qt.

**Spec:** `docs/superpowers/specs/2026-04-16-production-logger-design.md`

---

## File Structure

```
squid_tools/
├── logger.py                           # NEW: setup_logging, short_tag
├── __main__.py                         # MODIFY: call setup_logging before QApplication
├── gui/
│   ├── log_panel.py                    # MODIFY: QtLogHandler, level filter, backwards-compat log()
│   ├── app.py                          # MODIFY: add module logger + route hot-path errors
│   ├── controller.py                   # MODIFY: add module logger + emit INFO on load, ERROR on failure
│   └── algorithm_runner.py             # MODIFY: add module logger + emit INFO on run, ERROR on fail
├── viewer/
│   └── viewport_engine.py              # MODIFY: add module logger + DEBUG on cache/load, ERROR on read fail
└── processing/
    ├── flatfield/plugin.py             # MODIFY: add module logger + INFO on phase transitions
    └── stitching/plugin.py             # MODIFY: add module logger + INFO/WARNING per phase
tests/
├── unit/
│   ├── test_logger.py                  # NEW: setup_logging, short_tag, rotation, tempdir fallback
│   ├── test_gui_log_panel.py           # MODIFY: add QtLogHandler, level filter, logging integration tests
├── integration/
│   └── test_logger_integration.py      # NEW: cross-module logger → LogPanel console round-trip
```

---

### Task 1: logger.py — `setup_logging()` attaches rotating file handler + idempotence

**Files:**
- Create: `squid_tools/logger.py`
- Create: `tests/unit/test_logger.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_logger.py`:
```python
"""Tests for squid_tools.logger."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from squid_tools.logger import setup_logging


@pytest.fixture(autouse=True)
def _reset_root_logger():
    """Detach all handlers from the squid_tools root logger before/after each test."""
    root = logging.getLogger("squid_tools")
    for h in list(root.handlers):
        root.removeHandler(h)
    yield
    for h in list(root.handlers):
        root.removeHandler(h)


class TestSetupLogging:
    def test_returns_log_dir(self, tmp_path: Path) -> None:
        log_dir = setup_logging(log_dir=tmp_path / "logs")
        assert log_dir == tmp_path / "logs"
        assert log_dir.is_dir()

    def test_installs_rotating_file_handler(self, tmp_path: Path) -> None:
        setup_logging(log_dir=tmp_path / "logs")
        root = logging.getLogger("squid_tools")
        handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(handlers) == 1
        fh = handlers[0]
        assert fh.baseFilename == str(tmp_path / "logs" / "squid-tools.log")
        assert fh.maxBytes == 10 * 1024 * 1024
        assert fh.backupCount == 5
        assert fh.level == logging.DEBUG

    def test_root_level_debug(self, tmp_path: Path) -> None:
        setup_logging(log_dir=tmp_path / "logs")
        assert logging.getLogger("squid_tools").level == logging.DEBUG

    def test_idempotent(self, tmp_path: Path) -> None:
        setup_logging(log_dir=tmp_path / "logs")
        setup_logging(log_dir=tmp_path / "logs")
        root = logging.getLogger("squid_tools")
        # Calling twice should not stack handlers
        handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(handlers) == 1

    def test_message_written_to_file(self, tmp_path: Path) -> None:
        log_dir = setup_logging(log_dir=tmp_path / "logs")
        logging.getLogger("squid_tools.test").info("hello logger")
        # Flush handlers
        for h in logging.getLogger("squid_tools").handlers:
            h.flush()
        log_file = log_dir / "squid-tools.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert "hello logger" in content
        assert "[INFO]" in content
        assert "squid_tools.test" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_logger.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'squid_tools.logger'`

- [ ] **Step 3: Write minimal implementation**

`squid_tools/logger.py`:
```python
"""squid-tools logging setup.

Call setup_logging() once at app startup. All other code uses:

    import logging
    logger = logging.getLogger(__name__)
    logger.info("something")
    logger.debug("detailed thing")
    logger.error("failed: %s", reason)

Records go to a rotating file (DEBUG+) and to whatever handler the GUI
attaches to the 'squid_tools' logger (e.g. QtLogHandler in LogPanel).
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

FILE_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
_DEFAULT_LOG_DIR = Path.home() / ".squid-tools" / "logs"


def setup_logging(log_dir: Path | None = None) -> Path:
    """Configure the squid_tools root logger. Idempotent.

    Returns the log directory actually used.
    """
    if log_dir is None:
        log_dir = _DEFAULT_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("squid_tools")
    root.setLevel(logging.DEBUG)

    # Remove previously attached handlers so repeated calls are safe.
    for h in list(root.handlers):
        root.removeHandler(h)

    file_handler = RotatingFileHandler(
        log_dir / "squid-tools.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT))
    root.addHandler(file_handler)

    return log_dir
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_logger.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add squid_tools/logger.py tests/unit/test_logger.py
git commit -m "feat(logger): setup_logging installs rotating file handler (idempotent)"
```

---

### Task 2: logger.py — tempdir fallback when primary dir is unwritable

**Files:**
- Modify: `squid_tools/logger.py`
- Modify: `tests/unit/test_logger.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_logger.py`:
```python
class TestSetupLoggingFallback:
    def test_falls_back_to_tempdir_when_primary_unwritable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Pick a path whose parent doesn't exist and cannot be created.
        unwritable = tmp_path / "nope.txt"
        unwritable.write_text("not a dir")  # a file, not a directory
        target = unwritable / "logs"  # mkdir on this path will OSError

        log_dir = setup_logging(log_dir=target)

        # Must not be the unwritable target
        assert log_dir != target
        assert log_dir.is_dir()
        # Must still install a file handler that points inside the fallback
        root = logging.getLogger("squid_tools")
        file_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 1
        assert str(log_dir) in file_handlers[0].baseFilename
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_logger.py::TestSetupLoggingFallback -v`
Expected: FAIL — `NotADirectoryError` raised by `mkdir`

- [ ] **Step 3: Implement the fallback**

Edit `squid_tools/logger.py`. Replace the current `setup_logging` body with:

```python
from __future__ import annotations

import logging
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

FILE_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
_DEFAULT_LOG_DIR = Path.home() / ".squid-tools" / "logs"


def setup_logging(log_dir: Path | None = None) -> Path:
    """Configure the squid_tools root logger. Idempotent.

    Returns the log directory actually used (may be a tempdir fallback).
    """
    if log_dir is None:
        log_dir = _DEFAULT_LOG_DIR

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log_dir = Path(tempfile.gettempdir()) / "squid-tools-logs"
        log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("squid_tools")
    root.setLevel(logging.DEBUG)
    for h in list(root.handlers):
        root.removeHandler(h)

    file_handler = RotatingFileHandler(
        log_dir / "squid-tools.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT))
    root.addHandler(file_handler)

    return log_dir
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `pytest tests/unit/test_logger.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add squid_tools/logger.py tests/unit/test_logger.py
git commit -m "feat(logger): fallback to tempdir when primary log dir is unwritable"
```

---

### Task 3: logger.py — `short_tag()` console mapping

**Files:**
- Modify: `squid_tools/logger.py`
- Modify: `tests/unit/test_logger.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_logger.py`:
```python
from squid_tools.logger import short_tag


class TestShortTag:
    def test_viewer_module(self) -> None:
        assert short_tag("squid_tools.viewer.widget") == "viewer"

    def test_processing_module(self) -> None:
        assert short_tag("squid_tools.processing.flatfield.plugin") == "processing"

    def test_core_module(self) -> None:
        assert short_tag("squid_tools.core.cache") == "core"

    def test_gui_module(self) -> None:
        assert short_tag("squid_tools.gui.app") == "gui"

    def test_top_level(self) -> None:
        assert short_tag("squid_tools") == "squid_tools"

    def test_unknown_namespace(self) -> None:
        assert short_tag("thirdparty.module.submod") == "submod"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_logger.py::TestShortTag -v`
Expected: FAIL — `ImportError: cannot import name 'short_tag'`

- [ ] **Step 3: Implement `short_tag`**

Append to `squid_tools/logger.py`:
```python
def short_tag(logger_name: str) -> str:
    """Return the short component tag for console display.

    squid_tools.viewer.widget           -> viewer
    squid_tools.processing.flatfield.X  -> processing
    squid_tools.core.cache              -> core
    squid_tools.gui.app                 -> gui
    anything else                        -> last module component
    """
    parts = logger_name.split(".")
    if parts[:1] == ["squid_tools"] and len(parts) >= 2:
        return parts[1]
    return parts[-1]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_logger.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add squid_tools/logger.py tests/unit/test_logger.py
git commit -m "feat(logger): add short_tag() mapping for console display"
```

---

### Task 4: QtLogHandler — emits a Qt signal per log record

**Files:**
- Modify: `squid_tools/gui/log_panel.py`
- Modify: `tests/unit/test_gui_log_panel.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_gui_log_panel.py`:
```python
import logging

import pytest
from pytestqt.qtbot import QtBot


@pytest.fixture(autouse=True)
def _reset_root_logger():
    root = logging.getLogger("squid_tools")
    saved = list(root.handlers)
    yield
    for h in list(root.handlers):
        root.removeHandler(h)
    for h in saved:
        root.addHandler(h)


class TestQtLogHandler:
    def test_emits_record_emitted_signal(self, qtbot: QtBot) -> None:
        from squid_tools.gui.log_panel import QtLogHandler

        handler = QtLogHandler()
        handler.setLevel(logging.DEBUG)

        with qtbot.waitSignal(handler.record_emitted, timeout=500) as blocker:
            record = logging.LogRecord(
                name="squid_tools.viewer.widget",
                level=logging.INFO,
                pathname=__file__,
                lineno=1,
                msg="hello world",
                args=(),
                exc_info=None,
            )
            handler.emit(record)

        ts, level, tag, message = blocker.args
        assert isinstance(ts, str) and len(ts) == 8  # HH:MM:SS
        assert level == logging.INFO
        assert tag == "viewer"
        assert message == "hello world"

    def test_includes_traceback_when_exc_info_set(self, qtbot: QtBot) -> None:
        from squid_tools.gui.log_panel import QtLogHandler

        handler = QtLogHandler()
        handler.setLevel(logging.DEBUG)

        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        with qtbot.waitSignal(handler.record_emitted, timeout=500) as blocker:
            record = logging.LogRecord(
                name="squid_tools.gui.app",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="error happened",
                args=(),
                exc_info=exc_info,
            )
            handler.emit(record)

        _, _, _, message = blocker.args
        assert "error happened" in message
        assert "ValueError: boom" in message
        assert "Traceback" in message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_gui_log_panel.py::TestQtLogHandler -v`
Expected: FAIL — `ImportError: cannot import name 'QtLogHandler'`

- [ ] **Step 3: Implement `QtLogHandler`**

Edit `squid_tools/gui/log_panel.py`. Add these imports at the top (merge with existing):
```python
import logging
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal
```

Add this class just above `class LogPanel`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_gui_log_panel.py::TestQtLogHandler -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add squid_tools/gui/log_panel.py tests/unit/test_gui_log_panel.py
git commit -m "feat(log_panel): QtLogHandler emits record_emitted signal per record"
```

---

### Task 5: LogPanel — attach QtLogHandler, level filter, route `log()` through logging

**Files:**
- Modify: `squid_tools/gui/log_panel.py`
- Modify: `tests/unit/test_gui_log_panel.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_gui_log_panel.py`:
```python
class TestLogPanelLevelFilter:
    def test_default_level_is_info(self, qtbot: QtBot) -> None:
        from squid_tools.gui.log_panel import LogPanel

        panel = LogPanel()
        qtbot.addWidget(panel)
        assert panel._console_level == logging.INFO
        assert panel._level_filter.currentText() == "INFO"

    def test_logging_info_appears_in_console(self, qtbot: QtBot) -> None:
        from squid_tools.gui.log_panel import LogPanel

        panel = LogPanel()
        qtbot.addWidget(panel)
        logger = logging.getLogger("squid_tools.viewer.test")
        logger.info("visible info")
        text = panel._console.toPlainText()
        assert "visible info" in text
        assert "[INFO]" in text
        assert "[viewer]" in text

    def test_debug_hidden_at_info_level(self, qtbot: QtBot) -> None:
        from squid_tools.gui.log_panel import LogPanel

        panel = LogPanel()
        qtbot.addWidget(panel)
        logging.getLogger("squid_tools.viewer.test").debug("secret debug")
        assert "secret debug" not in panel._console.toPlainText()

    def test_debug_visible_when_level_changed_to_debug(self, qtbot: QtBot) -> None:
        from squid_tools.gui.log_panel import LogPanel

        panel = LogPanel()
        qtbot.addWidget(panel)
        panel._level_filter.setCurrentText("DEBUG")
        logging.getLogger("squid_tools.viewer.test").debug("now visible debug")
        assert "now visible debug" in panel._console.toPlainText()

    def test_warn_label_maps_to_warning(self, qtbot: QtBot) -> None:
        from squid_tools.gui.log_panel import LogPanel

        panel = LogPanel()
        qtbot.addWidget(panel)
        panel._level_filter.setCurrentText("WARN")
        # INFO should be hidden
        logging.getLogger("squid_tools.viewer.test").info("info hidden")
        # WARNING should be visible
        logging.getLogger("squid_tools.viewer.test").warning("warn visible")
        text = panel._console.toPlainText()
        assert "info hidden" not in text
        assert "warn visible" in text


class TestLogPanelLegacyLog:
    def test_legacy_log_routes_through_logging(self, qtbot: QtBot) -> None:
        from squid_tools.gui.log_panel import LogPanel

        panel = LogPanel()
        qtbot.addWidget(panel)
        panel.log("legacy message")
        text = panel._console.toPlainText()
        assert "legacy message" in text
        assert "[gui]" in text
        assert "[INFO]" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_gui_log_panel.py::TestLogPanelLevelFilter tests/unit/test_gui_log_panel.py::TestLogPanelLegacyLog -v`
Expected: FAIL (AttributeError `_console_level` / `_level_filter` / `[gui]` not found)

- [ ] **Step 3: Implement LogPanel refactor**

Edit `squid_tools/gui/log_panel.py`. Update imports:
```python
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
```

In `LogPanel.__init__`, add right after `self._gpu_label = QLabel(...)` and before `status_row.addWidget(self._status_label, ...)`:

```python
        self._console_level = logging.INFO
        self._level_filter = QComboBox()
        self._level_filter.addItems(["DEBUG", "INFO", "WARN", "ERROR"])
        self._level_filter.setCurrentText("INFO")
        self._level_filter.setToolTip(
            "Console log verbosity (file always captures DEBUG)"
        )
        self._level_filter.currentTextChanged.connect(self._on_level_changed)
```

Then add `self._level_filter` to the status_row right after the status_label (keep existing labels afterwards):
```python
        status_row.addWidget(self._status_label, stretch=2)
        status_row.addWidget(self._level_filter)
        status_row.addWidget(self._cache_label, stretch=2)
        status_row.addWidget(self._memory_label, stretch=1)
        status_row.addWidget(self._gpu_label, stretch=1)
```

After the memory polling setup (end of `__init__`), add:
```python
        self._qt_handler = QtLogHandler()
        self._qt_handler.setLevel(logging.DEBUG)
        self._qt_handler.record_emitted.connect(self._on_log_record)
        logging.getLogger("squid_tools").addHandler(self._qt_handler)
```

Replace the existing `log()` method:
```python
    def log(self, message: str) -> None:
        """Backwards-compat: route a plain string through Python logging at INFO."""
        logging.getLogger("squid_tools.gui").info(message)
```

Add new methods:
```python
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
```

- [ ] **Step 4: Run full LogPanel test file**

Run: `pytest tests/unit/test_gui_log_panel.py -v`
Expected: PASS (all existing + new tests). The existing `test_log_message` still passes because `log()` routes through logging, which emits via QtLogHandler (same-thread direct connection), which appends to the console synchronously.

- [ ] **Step 5: Commit**

```bash
git add squid_tools/gui/log_panel.py tests/unit/test_gui_log_panel.py
git commit -m "feat(log_panel): level-filter dropdown + QtLogHandler, legacy log() routes through logging"
```

---

### Task 6: `__main__.py` — call `setup_logging()` before `QApplication`

**Files:**
- Modify: `squid_tools/__main__.py`
- Modify: `tests/unit/test_entry.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_entry.py` (or create a new `TestLoggerWiring` class). If `test_entry.py` doesn't already import main, add:

```python
class TestLoggerWiring:
    def test_main_calls_setup_logging_before_qapplication(self, monkeypatch, tmp_path) -> None:
        import sys

        import squid_tools.__main__ as main_mod

        calls: list[str] = []

        def fake_setup(log_dir=None):
            calls.append("setup_logging")
            return tmp_path

        class FakeApp:
            def __init__(self, *a, **kw):
                calls.append("QApplication")
            def exec(self):
                return 0

        class FakeWindow:
            def __init__(self, *a, **kw):
                calls.append("MainWindow")
            def show(self):
                pass
            def open_acquisition(self, *a, **kw):
                pass
            controller = type("C", (), {"registry": type("R", (), {"register": staticmethod(lambda p: None)})(), "acquisition": None})()

        monkeypatch.setattr("squid_tools.logger.setup_logging", fake_setup)
        monkeypatch.setattr("PySide6.QtWidgets.QApplication", FakeApp)
        monkeypatch.setattr("squid_tools.gui.app.MainWindow", FakeWindow)
        monkeypatch.setattr("squid_tools.gui.style.apply_style", lambda app: None)
        monkeypatch.setattr(sys, "argv", ["squid-tools"])
        monkeypatch.setattr(sys, "exit", lambda *a, **kw: None)

        main_mod.main()

        assert calls.index("setup_logging") < calls.index("QApplication")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_entry.py::TestLoggerWiring -v`
Expected: FAIL — `setup_logging` not called.

- [ ] **Step 3: Wire `setup_logging()` into `__main__.main()`**

Edit `squid_tools/__main__.py`. Replace the body of `main()` with the version below — it calls `setup_logging()` right after argument parsing and before importing Qt.

```python
"""CLI entry point: python -m squid_tools."""

from __future__ import annotations

import argparse
import logging
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

    from squid_tools.logger import setup_logging  # noqa: PLC0415

    log_dir = setup_logging()
    logging.getLogger("squid_tools").info("Logging to %s", log_dir)

    import os  # noqa: PLC0415
    os.environ.setdefault("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", ""))

    from pathlib import Path  # noqa: PLC0415

    from PySide6.QtWidgets import QApplication  # noqa: PLC0415

    from squid_tools.gui.app import MainWindow  # noqa: PLC0415

    app = QApplication(sys.argv)
    from squid_tools.gui.style import apply_style  # noqa: PLC0415
    apply_style(app)
    window = MainWindow()

    if args.path:
        window.open_acquisition(Path(args.path))

    if args.dev and args.dev is not True:
        from squid_tools.gui.dev_panel import DevConsole, load_plugin_from_file  # noqa: PLC0415
        plugin_path = Path(args.dev)
        if plugin_path.exists():
            plugins = load_plugin_from_file(plugin_path)
            for p in plugins:
                window.controller.registry.register(p)
            dev_console = DevConsole()
            for p in plugins:
                dev_console.log(f"Loaded: {p.name} ({p.category})")
                warnings = (
                    p.validate(window.controller.acquisition)
                    if window.controller.acquisition
                    else []
                )
                for w in warnings:
                    dev_console.log(f"  Warning: {w}")
                dev_console.run_test_cases(p)
            dev_console.show()

    window.show()
    sys.exit(app.exec())


def _get_version() -> str:
    from squid_tools import __version__  # noqa: PLC0415

    return __version__


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_entry.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add squid_tools/__main__.py tests/unit/test_entry.py
git commit -m "feat(entry): call setup_logging() before QApplication in __main__"
```

---

### Task 7: Migrate `gui/controller.py` and `gui/algorithm_runner.py` to module loggers

**Files:**
- Modify: `squid_tools/gui/controller.py`
- Modify: `squid_tools/gui/algorithm_runner.py`
- Modify: `tests/unit/test_controller.py`
- Modify: `tests/unit/test_algorithm_runner.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_controller.py`:
```python
import logging


class TestControllerLogging:
    def test_load_emits_info_log(self, tmp_path, individual_acquisition, caplog):
        from squid_tools.gui.controller import AppController

        controller = AppController()
        caplog.set_level(logging.INFO, logger="squid_tools")
        controller.load_acquisition(individual_acquisition)
        messages = [r.getMessage() for r in caplog.records if r.name.startswith("squid_tools.gui.controller")]
        assert any("Loaded acquisition" in m for m in messages)

    def test_load_failure_emits_error_log(self, tmp_path, caplog):
        from squid_tools.gui.controller import AppController

        controller = AppController()
        caplog.set_level(logging.ERROR, logger="squid_tools")
        with pytest.raises(Exception):
            controller.load_acquisition(tmp_path / "does_not_exist")
        errors = [
            r for r in caplog.records
            if r.name.startswith("squid_tools.gui.controller") and r.levelno == logging.ERROR
        ]
        assert errors, "controller should log ERROR on failure"
```

Append to `tests/unit/test_algorithm_runner.py`:
```python
import logging


class TestAlgorithmRunnerLogging:
    def test_run_emits_info_log(self, qtbot, monkeypatch, caplog):
        from squid_tools.gui.algorithm_runner import AlgorithmRunner

        runner = AlgorithmRunner()
        caplog.set_level(logging.INFO, logger="squid_tools")

        class FakePlugin:
            name = "FakePlugin"
            def run_live(self, selection, engine, params, progress):
                progress("phase", 1, 1)

        started = runner.run(plugin=FakePlugin(), selection=None, engine=object(), params=object())
        assert started is True
        qtbot.waitUntil(lambda: not runner.is_running(), timeout=2000)

        infos = [
            r for r in caplog.records
            if r.name.startswith("squid_tools.gui.algorithm_runner") and r.levelno == logging.INFO
        ]
        assert any("FakePlugin" in r.getMessage() for r in infos)
```

If `test_controller.py` / `test_algorithm_runner.py` don't yet import `pytest`, add `import pytest` at the top.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_controller.py::TestControllerLogging tests/unit/test_algorithm_runner.py::TestAlgorithmRunnerLogging -v`
Expected: FAIL — no records on the controller / algorithm_runner loggers.

- [ ] **Step 3: Add module loggers**

Edit `squid_tools/gui/controller.py`. Add at the top under the existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

Replace `load_acquisition` with:
```python
    def load_acquisition(self, path: Path) -> Acquisition:
        """Load an acquisition directory. Auto-detects format."""
        try:
            self._reader = detect_reader(path)
            self.acquisition = self._reader.read_metadata(path)
            self.sidecar = SidecarManifest(acquisition_path=path)
            self.data_manager.load(path)
        except Exception:
            logger.exception("Failed to load acquisition at %s", path)
            raise
        logger.info(
            "Loaded acquisition %s (format=%s, regions=%d)",
            path,
            self.acquisition.format.value,
            len(self.acquisition.regions),
        )
        return self.acquisition
```

Edit `squid_tools/gui/algorithm_runner.py`. Add at the top, under existing imports:
```python
import logging

logger = logging.getLogger(__name__)
```

In `AlgorithmRunner.run`, after the `if self.is_running(): return False` check:
```python
        logger.info("Starting plugin run: %s", plugin.name)
```

In `_on_complete`, at the top:
```python
        logger.info("Plugin run complete: %s (%d tiles)", plugin_name, tiles_processed)
```

In `_on_failed`, at the top:
```python
        logger.error("Plugin run failed: %s — %s", plugin_name, error_message.splitlines()[0])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_controller.py tests/unit/test_algorithm_runner.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add squid_tools/gui/controller.py squid_tools/gui/algorithm_runner.py tests/unit/test_controller.py tests/unit/test_algorithm_runner.py
git commit -m "feat(logger): controller + algorithm_runner use module logger"
```

---

### Task 8: Migrate `viewer/viewport_engine.py` and plugins to module loggers

**Files:**
- Modify: `squid_tools/viewer/viewport_engine.py`
- Modify: `squid_tools/processing/flatfield/plugin.py`
- Modify: `squid_tools/processing/stitching/plugin.py`
- Modify: `tests/unit/test_viewport_engine.py`
- Modify: `tests/unit/test_stitcher_run_live.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_viewport_engine.py`:
```python
import logging


class TestViewportEngineLogging:
    def test_load_emits_debug_log(self, individual_acquisition, caplog):
        from squid_tools.viewer.viewport_engine import ViewportEngine

        caplog.set_level(logging.DEBUG, logger="squid_tools")
        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        debugs = [
            r for r in caplog.records
            if r.name.startswith("squid_tools.viewer.viewport_engine")
            and r.levelno == logging.DEBUG
        ]
        assert debugs, "engine.load should emit at least one DEBUG log"
```

Append to `tests/unit/test_stitcher_run_live.py` (create the class if it doesn't exist). Keep existing tests:
```python
import logging


class TestStitcherLogging:
    def test_run_live_emits_info_log(
        self, qtbot, individual_acquisition, caplog,
    ):
        from squid_tools.processing.stitching.plugin import StitcherPlugin
        from squid_tools.viewer.viewport_engine import ViewportEngine

        caplog.set_level(logging.INFO, logger="squid_tools")
        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        plugin = StitcherPlugin()
        params = plugin.default_params(None)

        def noop_progress(phase: str, current: int, total: int) -> None:
            pass

        plugin.run_live(
            selection=None, engine=engine, params=params, progress=noop_progress,
        )
        infos = [
            r for r in caplog.records
            if r.name.startswith("squid_tools.processing.stitching")
            and r.levelno == logging.INFO
        ]
        assert infos, "Stitcher run_live should log INFO phase transitions"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_viewport_engine.py::TestViewportEngineLogging tests/unit/test_stitcher_run_live.py::TestStitcherLogging -v`
Expected: FAIL — no records.

- [ ] **Step 3: Add module loggers and emit calls**

Edit `squid_tools/viewer/viewport_engine.py`. Add at the top of the module:
```python
import logging

logger = logging.getLogger(__name__)
```

In `ViewportEngine.load`, add at the end of the method (after the spatial index is built) a single:
```python
        logger.debug(
            "Loaded region=%s (FOVs=%d, bounds=%s)",
            region, len(self._fovs) if hasattr(self, "_fovs") else -1, self.bounding_box(),
        )
```

If the variable names differ (the file uses `self._index` etc.), adapt to whatever is available — the important thing is to emit one DEBUG record per load. Prefer existing public attributes over private ones. If `self.bounding_box()` raises because a region is empty, guard with a try/except that still emits the DEBUG log with a placeholder.

In `ViewportEngine._load_raw` (the read path), in the `except` branch (or wherever a read can fail), add:
```python
        logger.error("Frame read failed fov=%d z=%d channel=%d t=%d", fov, z, channel, timepoint)
```

Edit `squid_tools/processing/flatfield/plugin.py`. Add at the top:
```python
import logging

logger = logging.getLogger(__name__)
```

Inside `run_live`, at the start of the calibration phase:
```python
        logger.info("Flatfield: calibrating from %d tiles", sample_count)
```

And at the start of the apply phase:
```python
        logger.info("Flatfield: applying correction to %d tiles", total)
```

Use whatever variable names the current implementation exposes. If the plugin's `run_live` uses different phase names, adapt naming but keep the two INFO records (calibrate, apply).

Edit `squid_tools/processing/stitching/plugin.py`. Add at the top:
```python
import logging

logger = logging.getLogger(__name__)
```

Inside `run_live`, add:
- `logger.info("Stitcher: pairwise registration on %d tiles", ...)` at the start of pairwise phase
- `logger.warning("Stitcher: pair (%d, %d) failed", a, b)` in the per-pair failure branch
- `logger.info("Stitcher: global optimization (%d positions)", ...)` at the start of optimization

Use whatever variables the current file exposes; only the log messages are new.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_viewport_engine.py tests/unit/test_stitcher_run_live.py tests/unit/test_flatfield_run_live.py -v`
Expected: PASS (all existing + new logging tests)

- [ ] **Step 5: Commit**

```bash
git add squid_tools/viewer/viewport_engine.py squid_tools/processing/flatfield/plugin.py squid_tools/processing/stitching/plugin.py tests/unit/test_viewport_engine.py tests/unit/test_stitcher_run_live.py
git commit -m "feat(logger): viewport_engine + flatfield + stitching plugins emit via module logger"
```

---

### Task 9: Integration test — non-GUI logger records surface in LogPanel

**Files:**
- Create: `tests/integration/test_logger_integration.py`

- [ ] **Step 1: Write the failing test**

`tests/integration/test_logger_integration.py`:
```python
"""Integration: non-GUI modules log via Python logging; LogPanel shows them."""

from __future__ import annotations

import logging

import pytest
from pytestqt.qtbot import QtBot


@pytest.fixture(autouse=True)
def _reset_root_logger():
    root = logging.getLogger("squid_tools")
    saved = list(root.handlers)
    yield
    for h in list(root.handlers):
        root.removeHandler(h)
    for h in saved:
        root.addHandler(h)


class TestLoggerIntegration:
    def test_non_gui_module_info_appears_in_console(self, qtbot: QtBot) -> None:
        from squid_tools.gui.log_panel import LogPanel

        panel = LogPanel()
        qtbot.addWidget(panel)

        logger = logging.getLogger("squid_tools.viewer.viewport_engine")
        logger.info("engine says hi")

        text = panel._console.toPlainText()
        assert "engine says hi" in text
        assert "[viewer]" in text

    def test_debug_suppressed_at_default_console_level(self, qtbot: QtBot) -> None:
        from squid_tools.gui.log_panel import LogPanel

        panel = LogPanel()
        qtbot.addWidget(panel)
        logging.getLogger("squid_tools.processing.flatfield").debug("calibrate detail")
        assert "calibrate detail" not in panel._console.toPlainText()

    def test_debug_visible_after_level_change(self, qtbot: QtBot) -> None:
        from squid_tools.gui.log_panel import LogPanel

        panel = LogPanel()
        qtbot.addWidget(panel)
        panel._level_filter.setCurrentText("DEBUG")
        logging.getLogger("squid_tools.processing.flatfield").debug("now visible")
        assert "now visible" in panel._console.toPlainText()

    def test_error_traceback_rendered(self, qtbot: QtBot) -> None:
        from squid_tools.gui.log_panel import LogPanel

        panel = LogPanel()
        qtbot.addWidget(panel)
        logger = logging.getLogger("squid_tools.gui.app")
        try:
            raise RuntimeError("bad state")
        except RuntimeError:
            logger.exception("failure during X")

        text = panel._console.toPlainText()
        assert "failure during X" in text
        assert "RuntimeError: bad state" in text
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/integration/test_logger_integration.py -v`
Expected: PASS (all 4)

Because all the implementation landed in prior tasks, this test should already pass. If it doesn't, fix the underlying module; do not introduce new glue.

- [ ] **Step 3: Run the full test suite**

Run: `pytest -q`
Expected: PASS (all previous tests + 15+ new tests). No regressions.

- [ ] **Step 4: Run ruff**

Run: `ruff check squid_tools tests`
Expected: 0 errors. Fix in place if ruff flags anything (e.g., missing blank lines, unused imports).

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_logger_integration.py
git commit -m "test(logger): end-to-end cross-module logger → LogPanel integration"
```

---

## Self-Review

**Spec coverage:**
- `setup_logging()` with RotatingFileHandler, idempotent, tempdir fallback → Tasks 1-2 ✓
- `short_tag()` mapping → Task 3 ✓
- `QtLogHandler` signal-based → Task 4 ✓
- `LogPanel` level-filter dropdown + attach to root logger + backwards-compat `log()` → Task 5 ✓
- `__main__.py` wires `setup_logging()` before `QApplication` → Task 6 ✓
- Migration of `controller`, `algorithm_runner`, `viewport_engine`, `flatfield`, `stitching` → Tasks 7-8 ✓
- Integration (cross-module logger → console) → Task 9 ✓
- Tempdir fallback never blocks app startup → Task 2 ✓
- Error traceback inline when `exc_info` set → Tasks 4, 9 ✓

**Placeholder scan:** No "TODO", "TBD", or vague instructions — every step has code. The two places that say "Use whatever variable names the current implementation exposes" (Task 8) are bounded instructions: emit these specific log events at these specific phases; the implementer matches existing attribute names.

**Type consistency:** `short_tag`, `setup_logging`, `QtLogHandler.record_emitted(str, int, str, str)`, `LogPanel._on_log_record(ts, level, tag, message)`, `LogPanel._on_level_changed(text)` — signatures match across tasks.

**Scope:** Single subsystem (logging). Focused.

**Ambiguity:** Level dropdown labels: "WARN" shown in UI, mapped to `logging.WARNING` — handled explicitly in `_on_level_changed`. Qt signal direct-connection assumption (same thread) makes `log("msg")` land in the console synchronously, preserving the existing `test_log_message` behavior — called out in Task 5 Step 4.
