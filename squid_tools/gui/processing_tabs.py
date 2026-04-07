"""Processing tabs widget for the Squid-Tools GUI.

Auto-generates parameter widgets from plugin Pydantic models and hosts
each plugin in its own tab.
"""

from __future__ import annotations

import contextlib
from typing import Any

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QWidget,
)

from squid_tools.plugins.base import ProcessingPlugin


class PluginTab(QWidget):
    """Widget that auto-generates form inputs for a plugin's parameter model."""

    run_clicked = pyqtSignal(str, object)  # plugin name, BaseModel instance

    def __init__(self, plugin: ProcessingPlugin, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plugin = plugin
        self._param_cls = plugin.parameters()
        self._widgets: dict[str, QWidget] = {}

        outer = QHBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)

        # Scrollable form area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_container = QWidget()
        form_layout = QFormLayout(form_container)
        form_layout.setContentsMargins(4, 4, 4, 4)
        form_layout.setSpacing(4)
        scroll.setWidget(form_container)
        outer.addWidget(scroll, stretch=1)

        fields: dict[str, FieldInfo] = self._param_cls.model_fields

        for field_name, field_info in fields.items():
            annotation = field_info.annotation
            default = field_info.default

            widget: QWidget
            if annotation is bool or annotation == "bool":
                cb = QCheckBox()
                cb.setChecked(bool(default) if default is not None else False)
                cb.setToolTip(
                    field_info.description or f"Toggle {field_name}"
                )
                widget = cb
            elif annotation is int or annotation == "int":
                sb = QSpinBox()
                sb.setRange(-2_147_483_648, 2_147_483_647)
                if default is not None:
                    with contextlib.suppress(TypeError, ValueError):
                        sb.setValue(int(default))
                sb.setToolTip(field_info.description or f"Integer value for {field_name}")
                widget = sb
            else:
                # Default to float spinner for float and unknown types
                dsb = QDoubleSpinBox()
                dsb.setRange(-1e12, 1e12)
                dsb.setDecimals(4)
                if default is not None:
                    with contextlib.suppress(TypeError, ValueError):
                        dsb.setValue(float(default))
                dsb.setToolTip(field_info.description or f"Float value for {field_name}")
                widget = dsb

            self._widgets[field_name] = widget
            label = field_name.replace("_", " ").capitalize()
            form_layout.addRow(label, widget)

        # Run button
        self._run_btn = QPushButton("Run")
        self._run_btn.setToolTip(f"Run the '{plugin.name}' plugin with the current parameters")
        self._run_btn.clicked.connect(self._on_run)
        form_layout.addRow("", self._run_btn)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _collect_params(self) -> BaseModel:
        """Read widget values and construct a parameter model instance."""
        kwargs: dict[str, Any] = {}
        for field_name, widget in self._widgets.items():
            if isinstance(widget, QCheckBox):
                kwargs[field_name] = widget.isChecked()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                kwargs[field_name] = widget.value()
        return self._param_cls(**kwargs)

    def _on_run(self) -> None:
        params = self._collect_params()
        self.run_clicked.emit(self._plugin.name, params)


class ProcessingTabs(QTabWidget):
    """Tab widget hosting one PluginTab per registered plugin."""

    run_requested = pyqtSignal(str, object)  # plugin name, BaseModel instance

    _MAX_HEIGHT = 200

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMaximumHeight(self._MAX_HEIGHT)
        self.setToolTip("Processing plugins – configure parameters and run each plugin")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_plugin(self, plugin: ProcessingPlugin) -> None:
        """Create a PluginTab for *plugin* and append it as a new tab."""
        tab = PluginTab(plugin)
        tab.run_clicked.connect(self.run_requested)
        label = getattr(plugin, "name", type(plugin).__name__)
        self.addTab(tab, label)
