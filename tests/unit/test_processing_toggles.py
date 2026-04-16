"""Tests for toggle-based processing tabs."""

from pydantic import BaseModel
from pytestqt.qtbot import QtBot

from squid_tools.core.registry import PluginRegistry
from squid_tools.gui.processing_tabs import ProcessingTabs
from squid_tools.processing.base import ProcessingPlugin


class ScaleParams(BaseModel):
    factor: float = 2.0


class ScalePlugin(ProcessingPlugin):
    name = "Scale"
    category = "correction"

    def parameters(self):
        return ScaleParams

    def validate(self, acq):
        return []

    def process(self, frames, params):
        return frames * params.factor

    def default_params(self, optical=None):
        return ScaleParams()

    def test_cases(self):
        return []


class TestProcessingToggles:
    def test_tabs_have_toggles_not_buttons(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        registry.register(ScalePlugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        # Should have a toggle, not a "Run" button
        tab = tabs.widget(0)
        from PySide6.QtWidgets import QPushButton
        buttons = tab.findChildren(QPushButton)
        button_texts = [b.text() for b in buttons]
        assert "Run" not in button_texts

    def test_toggle_emits_signal(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        registry.register(ScalePlugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        with qtbot.waitSignal(tabs.toggle_changed, timeout=1000):
            tabs.set_toggle("Scale", True)

    def test_toggle_on_off(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        registry.register(ScalePlugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        tabs.set_toggle("Scale", True)
        assert tabs.is_active("Scale")
        tabs.set_toggle("Scale", False)
        assert not tabs.is_active("Scale")

    def test_active_plugins_list(self, qtbot: QtBot) -> None:
        registry = PluginRegistry()
        registry.register(ScalePlugin())
        tabs = ProcessingTabs(registry)
        qtbot.addWidget(tabs)
        assert tabs.active_plugin_names() == []
        tabs.set_toggle("Scale", True)
        assert "Scale" in tabs.active_plugin_names()
