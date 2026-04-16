"""Tests for log panel widget."""

from pytestqt.qtbot import QtBot

from squid_tools.gui.log_panel import LogPanel


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
