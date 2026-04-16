"""Tests for controls panel widget."""

from pytestqt.qtbot import QtBot

from squid_tools.gui.controls import ControlsPanel


class TestControlsPanel:
    def test_instantiate(self, qtbot: QtBot) -> None:
        panel = ControlsPanel()
        qtbot.addWidget(panel)
        assert panel is not None

    def test_has_borders_checkbox(self, qtbot: QtBot) -> None:
        panel = ControlsPanel()
        qtbot.addWidget(panel)
        assert panel.borders_checkbox is not None

    def test_borders_emits_signal(self, qtbot: QtBot) -> None:
        panel = ControlsPanel()
        qtbot.addWidget(panel)
        with qtbot.waitSignal(panel.borders_toggled, timeout=1000):
            panel.borders_checkbox.click()

    def test_borders_default_checked(self, qtbot: QtBot) -> None:
        panel = ControlsPanel()
        qtbot.addWidget(panel)
        assert panel.borders_checkbox.isChecked()
