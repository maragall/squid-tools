"""Tests for log panel widget."""

import logging

import pytest
from pytestqt.qtbot import QtBot

from squid_tools.gui.log_panel import LogPanel


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


class TestLogPanel:
    def test_instantiate(self, qtbot: QtBot) -> None:
        panel = LogPanel()
        qtbot.addWidget(panel)
        assert panel is not None

    def test_log_message(self, qtbot: QtBot) -> None:
        panel = LogPanel()
        qtbot.addWidget(panel)
        panel.log("Test message")
        assert "Test message" in panel.text()

    def test_set_status(self, qtbot: QtBot) -> None:
        panel = LogPanel()
        qtbot.addWidget(panel)
        panel.set_status("Ready")
        assert "Ready" in panel.status_text()

    def test_set_gpu_info(self, qtbot: QtBot) -> None:
        panel = LogPanel()
        qtbot.addWidget(panel)
        panel.set_gpu_info("NVIDIA RTX 3080")
        assert "RTX 3080" in panel.gpu_text()

    def test_set_memory_info(self, qtbot: QtBot) -> None:
        panel = LogPanel()
        qtbot.addWidget(panel)
        panel.set_memory_info(2.1, 16.0)
        assert "2.1" in panel.memory_text()


class TestLogPanelGPUIntegration:
    def test_auto_detects_gpu_on_init(self, qtbot: QtBot) -> None:
        panel = LogPanel()
        qtbot.addWidget(panel)
        gpu_text = panel.gpu_text()
        # Should contain either a GPU name or "CPU only"
        assert "GPU:" in gpu_text
        assert len(gpu_text) > 5  # "GPU: " + something
