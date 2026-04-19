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
        handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(handlers) == 1

    def test_message_written_to_file(self, tmp_path: Path) -> None:
        log_dir = setup_logging(log_dir=tmp_path / "logs")
        logging.getLogger("squid_tools.test").info("hello logger")
        for h in logging.getLogger("squid_tools").handlers:
            h.flush()
        log_file = log_dir / "squid-tools.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert "hello logger" in content
        assert "[INFO]" in content
        assert "squid_tools.test" in content


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
