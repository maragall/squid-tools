"""Processing tabs with toggle-based pipeline control.

Each plugin gets a tab with a toggle switch and parameter widgets.
Toggling ON inserts the plugin into the live processing pipeline.
Toggling OFF removes it. No Run button. No progress bar.
The mosaic updates when toggles change.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from squid_tools.core.registry import PluginRegistry
from squid_tools.processing.base import ProcessingPlugin


class ProcessingTabs(QTabWidget):
    """Tab widget with toggle per plugin. No Run buttons."""

    toggle_changed = Signal(str, bool)  # (plugin_name, is_active)

    def __init__(self, registry: PluginRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._registry = registry
        self._plugin_tabs: dict[str, _PluginTab] = {}

        for plugin in registry.list_all():
            tab = _PluginTab(plugin, self)
            tab.toggled.connect(lambda active, name=plugin.name: self._on_toggle(name, active))
            self.addTab(tab, plugin.name)
            self._plugin_tabs[plugin.name] = tab

    def set_toggle(self, plugin_name: str, active: bool) -> None:
        """Programmatically toggle a plugin."""
        if plugin_name in self._plugin_tabs:
            self._plugin_tabs[plugin_name].set_active(active)

    def is_active(self, plugin_name: str) -> bool:
        """Check if a plugin is currently toggled on."""
        if plugin_name in self._plugin_tabs:
            return self._plugin_tabs[plugin_name].is_active()
        return False

    def active_plugin_names(self) -> list[str]:
        """Return list of currently active plugin names."""
        return [name for name, tab in self._plugin_tabs.items() if tab.is_active()]

    def get_params(self, plugin_name: str) -> dict[str, Any]:
        """Get current parameter values for a plugin."""
        if plugin_name in self._plugin_tabs:
            return self._plugin_tabs[plugin_name].get_params()
        return {}

    def tab_text(self, index: int) -> str:
        """Return tab text for given index."""
        return self.tabText(index)

    def _on_toggle(self, plugin_name: str, active: bool) -> None:
        self.toggle_changed.emit(plugin_name, active)


class _PluginTab(QWidget):
    """Single plugin tab with toggle and parameter widgets."""

    toggled = Signal(bool)

    def __init__(self, plugin: ProcessingPlugin, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plugin = plugin
        self._param_widgets: dict[str, QWidget] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Toggle row
        toggle_row = QHBoxLayout()
        self._toggle = QCheckBox()
        self._toggle.setToolTip(f"Enable {plugin.name}")
        self._toggle.toggled.connect(self.toggled.emit)
        toggle_row.addWidget(self._toggle)
        toggle_row.addWidget(QLabel(plugin.name))
        toggle_row.addStretch()
        layout.addLayout(toggle_row)

        # Parameter widgets
        params_model = plugin.parameters()
        form = QFormLayout()

        for field_name, field_info in params_model.model_fields.items():
            annotation = field_info.annotation
            default = field_info.default
            widget: QWidget

            if annotation is float:
                spin = QDoubleSpinBox()
                spin.setRange(-1e6, 1e6)
                spin.setDecimals(3)
                if isinstance(default, (int, float)):
                    spin.setValue(float(default))
                spin.setToolTip(field_info.description or field_name)
                widget = spin
            elif annotation is int:
                spin_int = QSpinBox()
                spin_int.setRange(0, 100000)
                if isinstance(default, int):
                    spin_int.setValue(default)
                spin_int.setToolTip(field_info.description or field_name)
                widget = spin_int
            else:
                continue

            self._param_widgets[field_name] = widget
            form.addRow(field_name, widget)

        layout.addLayout(form)
        layout.addStretch()

    def set_active(self, active: bool) -> None:
        self._toggle.setChecked(active)

    def is_active(self) -> bool:
        return self._toggle.isChecked()

    def get_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {}
        for name, widget in self._param_widgets.items():
            if isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                params[name] = widget.value()
        return params
