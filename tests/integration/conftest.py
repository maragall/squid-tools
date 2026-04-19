"""Shared fixtures for integration tests."""

from __future__ import annotations

import logging

import pytest


@pytest.fixture(autouse=True)
def _detach_qt_log_handlers_after_test():
    """Prevent QtLogHandler instances from leaking across integration tests.

    MainWindow/LogPanel attach a QtLogHandler to the squid_tools root logger
    in __init__ but only detach in closeEvent, which qtbot doesn't always
    trigger. This fixture detaches any surviving QtLogHandler instances after
    each test runs.
    """
    yield
    from squid_tools.gui.log_panel import QtLogHandler

    root = logging.getLogger("squid_tools")
    for h in list(root.handlers):
        if isinstance(h, QtLogHandler):
            root.removeHandler(h)
