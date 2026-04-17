"""Tests for toggle + Run button + status processing tabs."""

import numpy as np
from pydantic import BaseModel
from pytestqt.qtbot import QtBot

from squid_tools.core.registry import PluginRegistry
from squid_tools.gui.processing_tabs import ProcessingTabs
from squid_tools.processing.base import ProcessingPlugin


class _Params(BaseModel):
    value: float = 1.0


class _Plugin(ProcessingPlugin):
    name = "Demo"
    category = "correction"
    requires_gpu = False

    def parameters(self) -> type[BaseModel]:
        return _Params

    def validate(self, acq) -> list[str]:
        return []

    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        return frames

    def default_params(self, optical) -> BaseModel:
        return _Params()

    def test_cases(self) -> list[dict]:
        return []


class TestProcessingTabsRunButton:
    def test_has_toggle_and_run_button(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        registry.register(_Plugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        from PySide6.QtWidgets import QCheckBox, QPushButton
        tab = tabs.widget(0)
        assert tab.findChildren(QCheckBox)
        assert tab.findChildren(QPushButton)

    def test_run_requested_signal(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        registry.register(_Plugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        with qtbot.waitSignal(tabs.run_requested, timeout=500) as blocker:
            tabs.click_run("Demo")
        assert blocker.args[0] == "Demo"
        # Second arg is params dict
        assert isinstance(blocker.args[1], dict)

    def test_set_status(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        registry.register(_Plugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        tabs.set_status("Demo", "Calibrating...")
        assert tabs.status_text("Demo") == "Calibrating..."

    def test_auto_run_on_first_toggle(self, qtbot: QtBot) -> None:
        """First toggle ON of an uncalibrated plugin should emit run_requested."""
        registry = PluginRegistry()
        registry.register(_Plugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        with qtbot.waitSignal(tabs.run_requested, timeout=500):
            tabs.set_toggle("Demo", True)

    def test_second_toggle_on_after_calibration_no_autorun(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        registry.register(_Plugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        # Mark as calibrated
        tabs.mark_calibrated("Demo")

        received = []
        tabs.run_requested.connect(lambda n, p: received.append(n))
        # Turn off then on — should NOT trigger run_requested
        tabs.set_toggle("Demo", False)
        tabs.set_toggle("Demo", True)
        assert received == []

    def test_toggle_changed_signal_still_emitted(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        registry.register(_Plugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        tabs.mark_calibrated("Demo")  # prevent auto-run
        with qtbot.waitSignal(tabs.toggle_changed, timeout=500) as blocker:
            tabs.set_toggle("Demo", True)
        assert blocker.args == ["Demo", True]
