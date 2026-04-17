"""Tests for processing tabs widget."""

import numpy as np
from pydantic import BaseModel
from pytestqt.qtbot import QtBot

from squid_tools.core.data_model import Acquisition, OpticalMetadata
from squid_tools.core.registry import PluginRegistry
from squid_tools.gui.processing_tabs import ProcessingTabs
from squid_tools.processing.base import ProcessingPlugin


class SigmaParams(BaseModel):
    sigma: float = 1.5
    iterations: int = 10


class DummyPlugin(ProcessingPlugin):
    name = "TestBlur"
    category = "correction"
    requires_gpu = False

    def parameters(self) -> type[BaseModel]:
        return SigmaParams

    def validate(self, acq: Acquisition) -> list[str]:
        return []

    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        return frames

    def default_params(self, optical: OpticalMetadata) -> BaseModel:
        return SigmaParams()

    def test_cases(self) -> list[dict]:
        return []


class TestProcessingTabs:
    def test_instantiate_empty(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        assert tabs.count() == 0

    def test_one_plugin_one_tab(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        registry.register(DummyPlugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        assert tabs.count() == 1

    def test_tab_has_toggle_and_run_button(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        registry.register(DummyPlugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        assert tabs.tab_text(0) == "TestBlur"
        # Has Run button
        from PySide6.QtWidgets import QCheckBox, QPushButton
        tab = tabs.widget(0)
        assert tab.findChildren(QCheckBox)
        assert tab.findChildren(QPushButton)

    def test_toggle_emits_signal(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        registry.register(DummyPlugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        with qtbot.waitSignal(tabs.toggle_changed, timeout=1000):
            tabs.set_toggle("TestBlur", True)

    def test_tab_text_matches_plugin_name(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        registry.register(DummyPlugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        assert tabs.tabText(0) == "TestBlur"
