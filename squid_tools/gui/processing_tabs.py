"""Processing tabs with toggle + Run button + status line per plugin.

Toggle = enable algorithm in the active pipeline (persistent).
Run    = trigger one-time calibration / computation (expensive).
Status = shows the current state ("Not calibrated" / "Applied to N tiles").

First toggle ON auto-triggers Run (so the user doesn't need to click twice
on first use).
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
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from squid_tools.core.registry import PluginRegistry
from squid_tools.processing.base import ProcessingPlugin


class ProcessingTabs(QTabWidget):
    """Tab widget: toggle + Run button + status per plugin."""

    toggle_changed = Signal(str, bool)     # (plugin_name, is_active)
    run_requested = Signal(str, object)    # (plugin_name, params_dict)

    def __init__(
        self,
        registry: PluginRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = registry
        self._plugin_tabs: dict[str, _PluginTab] = {}
        self._calibrated: dict[str, bool] = {}

        for plugin in registry.list_all():
            tab = _PluginTab(plugin, self)
            tab.toggled.connect(
                lambda active, name=plugin.name: self._on_toggle(name, active)
            )
            tab.run_clicked.connect(
                lambda name=plugin.name: self._on_run_click(name)
            )
            self.addTab(tab, plugin.name)
            self._plugin_tabs[plugin.name] = tab
            self._calibrated[plugin.name] = False

    def set_toggle(self, plugin_name: str, active: bool) -> None:
        """Programmatically toggle a plugin."""
        if plugin_name in self._plugin_tabs:
            self._plugin_tabs[plugin_name].set_active(active)

    def is_active(self, plugin_name: str) -> bool:
        if plugin_name in self._plugin_tabs:
            return self._plugin_tabs[plugin_name].is_active()
        return False

    def active_plugin_names(self) -> list[str]:
        return [
            name for name, tab in self._plugin_tabs.items() if tab.is_active()
        ]

    def get_params(self, plugin_name: str) -> dict[str, Any]:
        if plugin_name in self._plugin_tabs:
            return self._plugin_tabs[plugin_name].get_params()
        return {}

    def tab_text(self, index: int) -> str:
        """Return tab text for given index."""
        return self.tabText(index)

    def set_status(self, plugin_name: str, text: str) -> None:
        if plugin_name in self._plugin_tabs:
            self._plugin_tabs[plugin_name].set_status(text)

    def status_text(self, plugin_name: str) -> str:
        if plugin_name in self._plugin_tabs:
            return self._plugin_tabs[plugin_name].status_text()
        return ""

    def mark_calibrated(self, plugin_name: str) -> None:
        """Record that this plugin has completed its calibration."""
        self._calibrated[plugin_name] = True

    def click_run(self, plugin_name: str) -> None:
        """Programmatically click the Run button."""
        if plugin_name in self._plugin_tabs:
            self._plugin_tabs[plugin_name].click_run()

    def _on_toggle(self, plugin_name: str, active: bool) -> None:
        self.toggle_changed.emit(plugin_name, active)
        # Auto-run on first toggle ON (not yet calibrated)
        if active and not self._calibrated.get(plugin_name, False):
            self._emit_run(plugin_name)

    def _on_run_click(self, plugin_name: str) -> None:
        self._emit_run(plugin_name)

    def _emit_run(self, plugin_name: str) -> None:
        params = self.get_params(plugin_name)
        self.run_requested.emit(plugin_name, params)


class _PluginTab(QWidget):
    """Tab for one plugin: toggle + params + Run button + status line."""

    toggled = Signal(bool)
    run_clicked = Signal()

    def __init__(
        self,
        plugin: ProcessingPlugin,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._plugin = plugin
        self._param_widgets: dict[str, QWidget] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Toggle row
        toggle_row = QHBoxLayout()
        self._toggle = QCheckBox(f"Apply {plugin.name} to viewer")
        self._toggle.setToolTip(
            f"Apply {plugin.name} correction to tiles shown in the viewer. "
            "First check auto-runs calibration."
        )
        self._toggle.toggled.connect(self.toggled.emit)
        toggle_row.addWidget(self._toggle)
        toggle_row.addStretch()
        layout.addLayout(toggle_row)

        # Parameter widgets
        form = QFormLayout()
        params_cls = plugin.parameters()
        for field_name, field_info in params_cls.model_fields.items():
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

        # Run button + status
        button_row = QHBoxLayout()
        self._run_button = QPushButton("Calibrate / Compute")
        self._run_button.setToolTip(
            f"Run {plugin.name}'s calibration / computation on the current selection "
            "(or all FOVs if nothing selected)."
        )
        self._run_button.clicked.connect(self.run_clicked.emit)
        button_row.addWidget(self._run_button)
        button_row.addStretch()
        layout.addLayout(button_row)

        self._status_label = QLabel("Not calibrated")
        self._status_label.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(self._status_label)

        layout.addStretch()

    def set_active(self, active: bool) -> None:
        self._toggle.setChecked(active)

    def is_active(self) -> bool:
        return self._toggle.isChecked()

    def set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def status_text(self) -> str:
        return self._status_label.text()

    def click_run(self) -> None:
        self._run_button.click()

    def get_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {}
        for name, widget in self._param_widgets.items():
            if isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                params[name] = widget.value()
        return params
