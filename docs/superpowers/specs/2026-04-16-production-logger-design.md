# Production Logger Design Spec

## Purpose

Replace the ad-hoc `log_panel.log(...)` calls with Python's standard `logging` module so that all code (GUI, core, processing plugins, viewer internals) can log. Route records to both a rotating log file (for post-mortem debugging) and the GUI log console (for live user feedback).

**Audience:** Life-sciences users who need to understand what the app is doing right now, and developers who need to investigate crashes after the fact.

**Guiding principle:** The log is honest. When the app does something, the log records it. When something fails, the log explains it. The user's default console is quiet enough to be useful and loud enough to build trust.

---

## Scope

**IN:**
- `squid_tools/logger.py` with `setup_logging(log_dir)` entry point
- `RotatingFileHandler` at `~/.squid-tools/logs/squid-tools.log`, 10 MB × 5 backups, DEBUG+, full module-path formatter
- `QtLogHandler` subclass of `logging.Handler` that emits a Qt signal per record
- `LogPanel` refactor: handle log records via the Qt signal, console level filter dropdown (DEBUG / INFO / WARN / ERROR), default INFO
- Short tag mapping (`squid_tools.viewer.*` → `viewer`, etc.) for console display
- Backwards-compatible `log_panel.log(msg)` preserved (routes through the Python logger)
- Migrate a handful of non-GUI hot paths to use `logger.debug/info/warning/error` (engine, runner, plugins)
- `__main__.py` calls `setup_logging()` before `QApplication`
- Fallback behavior if log directory can't be created (use tempdir; never block app startup)

**OUT (future cycles):**
- Color-coded log lines (WARN yellow, ERROR red)
- Search / filter text box
- Per-component tag filtering UI (checkboxes)
- Click-to-copy traceback from log entries
- Detachable log window
- Export-to-file button in GUI (the file is already on disk)
- Per-level sound alerts
- Remote log aggregation (Sentry / similar)

---

## Architecture

```
Any module in squid_tools:
    logger = logging.getLogger(__name__)
    logger.info("something happened")
        |
        v
"squid_tools" root logger (level=DEBUG)
    |
    +--> RotatingFileHandler (DEBUG+, full format, ~/.squid-tools/logs/...)
    |
    +--> QtLogHandler (DEBUG+, emits record_emitted signal)
             |
             v
        LogPanel._on_log_record (filters by console_level, default INFO)
             |
             v
        QPlainTextEdit console with short-tag format

Legacy: log_panel.log(msg) -> logging.getLogger("squid_tools.gui").info(msg)
        (so existing GUI code keeps working unchanged)
```

The setup is idempotent — repeated `setup_logging()` calls remove previously installed handlers before attaching new ones. This lets tests reconfigure freely.

---

## Components

### 1. `squid_tools/logger.py`

```python
"""squid-tools logging setup.

Call setup_logging() once at app startup. All other code uses:

    import logging
    logger = logging.getLogger(__name__)
    logger.info("something")
    logger.debug("detailed thing")
    logger.error("failed: %s", reason)

Records go to a rotating file (DEBUG+) and to whatever Qt handler
the GUI attaches to the 'squid_tools' logger.
"""

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

    # Remove any previously attached handlers (so repeated calls are safe)
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

### 2. `QtLogHandler` (inside `squid_tools/gui/log_panel.py`)

```python
import logging
from datetime import datetime
from PySide6.QtCore import QObject, Signal


class QtLogHandler(QObject, logging.Handler):
    """Logging handler that emits a Qt signal per record.

    Must subclass QObject for signals. Multiple-inheritance with
    logging.Handler is fine because Handler is a pure-Python class.
    """

    record_emitted = Signal(str, int, str, str)
    # (timestamp_str, level_int, short_tag_str, message_str)

    def __init__(self) -> None:
        QObject.__init__(self)
        logging.Handler.__init__(self)

    def emit(self, record: logging.LogRecord) -> None:
        from squid_tools.logger import short_tag
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        tag = short_tag(record.name)
        msg = record.getMessage()
        # Append traceback inline if present
        if record.exc_info:
            tb = logging.Formatter().formatException(record.exc_info)
            msg = f"{msg}\n{tb}"
        self.record_emitted.emit(ts, record.levelno, tag, msg)
```

### 3. `LogPanel` refactor

```python
# squid_tools/gui/log_panel.py (modifications)

import logging
from PySide6.QtWidgets import QComboBox

# Inside LogPanel.__init__():
    self._console_level = logging.INFO

    # Level filter (added to status row)
    self._level_filter = QComboBox()
    self._level_filter.addItems(["DEBUG", "INFO", "WARN", "ERROR"])
    self._level_filter.setCurrentText("INFO")
    self._level_filter.setToolTip("Console log verbosity (file always captures DEBUG)")
    self._level_filter.currentTextChanged.connect(self._on_level_changed)
    status_row.addWidget(self._level_filter)

    # Qt log handler attached to the squid_tools root logger
    self._qt_handler = QtLogHandler()
    self._qt_handler.setLevel(logging.DEBUG)
    self._qt_handler.record_emitted.connect(self._on_log_record)
    logging.getLogger("squid_tools").addHandler(self._qt_handler)

# New methods:
def _on_log_record(
    self, ts: str, level: int, tag: str, message: str,
) -> None:
    if level < self._console_level:
        return
    level_name = logging.getLevelName(level)
    self._console.appendPlainText(f"[{ts}] [{level_name}] [{tag}] {message}")

def _on_level_changed(self, text: str) -> None:
    mapping = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    self._console_level = mapping.get(text, logging.INFO)

# Modified log() — backwards compat:
def log(self, message: str) -> None:
    """Legacy API preserved. Routes through Python logging at INFO."""
    logging.getLogger("squid_tools.gui").info(message)

# When panel is destroyed, detach the Qt handler
def closeEvent(self, event):  # noqa: N802
    try:
        logging.getLogger("squid_tools").removeHandler(self._qt_handler)
    finally:
        super().closeEvent(event)
```

### 4. Migration of non-GUI code

These files/paths get `logger = logging.getLogger(__name__)` and emit via the new logger:

- `squid_tools/gui/algorithm_runner.py` — INFO on run start, run complete; ERROR on run failed (with exception info)
- `squid_tools/viewer/viewport_engine.py` — DEBUG on load, compute_contrast, cache hit/miss; ERROR on frame read failure
- `squid_tools/processing/flatfield/plugin.py` — INFO at phase transitions; DEBUG per sample tile
- `squid_tools/processing/stitching/plugin.py` — INFO at phase transitions; DEBUG per registered pair; WARNING if a pair fails
- `squid_tools/gui/controller.py` — INFO on acquisition load; ERROR on reader failure

These are the only files modified in this cycle for migration. Other modules can adopt the logger incrementally in later cycles.

### 5. `__main__.py` wires setup

```python
# squid_tools/__main__.py — modification
def main() -> None:
    import argparse
    import sys

    from squid_tools.logger import setup_logging

    log_dir = setup_logging()
    logger = logging.getLogger("squid_tools")
    logger.info("Logging to %s", log_dir)

    # ... rest of main unchanged ...
```

---

## Data Flow

1. Any code calls `logger.info("X")`
2. Record propagates up the `squid_tools.*` tree to root
3. Root has two handlers:
   - File handler writes `2026-04-16 14:23:05 [INFO] [squid_tools.viewer.widget] X` to rotating file
   - Qt handler emits `record_emitted("14:23:05", 20, "viewer", "X")`
4. LogPanel receives the signal, filters by `_console_level`, appends `[14:23:05] [INFO] [viewer] X` to the console

Backwards-compat path: `log_panel.log("X")` → `logger.getLogger("squid_tools.gui").info("X")` → same as above, tagged as `gui`.

---

## Error Handling

| Failure | Behavior |
|---------|----------|
| Log dir can't be created (permission, disk full) | Fall back to tempdir. Never raise. |
| Tempdir also fails | Log only to stderr via a StreamHandler added as fallback. App still starts. |
| Qt handler fires before LogPanel exists | The handler is attached IN LogPanel's `__init__`, so this can't happen in normal flow. |
| QPlainTextEdit internal error | Caught by `Handler.handleError` (logging's default). Record dropped, not re-raised. |
| Log file reaches 10 MB | `RotatingFileHandler` rolls to `.1`, `.2`, ... up to 5 backups. Oldest dropped automatically. |

The logger setup is isolated from the rest of startup. If logging is broken, the app still runs (without observable logs).

---

## UX Details

**Default console state (INFO):**
```
[14:23:05] [INFO] [gui] Loading: /Users/.../10x_mouse_brain_...
[14:23:05] [INFO] [gui] Format: INDIVIDUAL_IMAGES | Objective: 10x (0.752 um/px) | Regions: 1 | FOVs: 70 | Channels: 4
[14:23:07] [INFO] [viewer] Loaded region 0 (70 FOVs)
[14:23:12] [INFO] [gui] 24 tiles selected
[14:23:15] [INFO] [processing] Flatfield: Calibrating 0/20
[14:23:17] [INFO] [processing] Flatfield: Applied to 70 tiles
```

**DEBUG mode** (user changes dropdown):
```
[14:23:12] [DEBUG] [viewer] viewport bounds: (10.5, 8.3, 25.7, 20.1) mm
[14:23:12] [DEBUG] [viewer] visible FOVs: {0, 1, 2, 4, 5}
[14:23:12] [DEBUG] [viewer] cache hit for fov=4
[14:23:12] [DEBUG] [viewer] cache miss for fov=5, reading from disk
```

**ERROR state:**
```
[14:23:20] [ERROR] [processing] Stitcher: pair (3, 7) failed
Traceback (most recent call last):
  ...
```

Level dropdown sits next to the existing memory/GPU status row. Compact single-select combo box, no label (its position makes its purpose obvious).

---

## Testing Plan

**(Written at end of all cycles — functional user workflow tests for the complete integrated product. Per-cycle TDD is handled by superpowers during implementation.)**

Placeholder: this cycle's TDD tests live in its implementation plan. The spec's Testing Plan section will be written when all planned cycles are complete, describing end-to-end user workflows to validate the full product.
