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
        logging.getLogger("squid_tools.processing.flatfield").debug(
            "calibrate detail"
        )
        assert "calibrate detail" not in panel._console.toPlainText()

    def test_debug_visible_after_level_change(self, qtbot: QtBot) -> None:
        from squid_tools.gui.log_panel import LogPanel

        panel = LogPanel()
        qtbot.addWidget(panel)
        panel._level_filter.setCurrentText("DEBUG")
        logging.getLogger("squid_tools.processing.flatfield").debug(
            "now visible"
        )
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
