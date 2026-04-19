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
