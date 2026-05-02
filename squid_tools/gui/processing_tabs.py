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

    # Category → human-readable umbrella tab label. A plugin's
    # category attribute groups it under one of these tabs. Unknown
    # categories fall through to category.title().
    CATEGORY_LABELS: dict[str, str] = {
        "shading": "Shading",
        "denoising": "Denoising",
        "background": "Background",
        "deconvolution": "Deconvolution",
        "phase": "Phase",
        "stitching": "Stitching",
        "correction": "Correction",
    }

    # Display order of umbrella tabs (most-used first).
    CATEGORY_ORDER: list[str] = [
        "shading", "denoising", "background",
        "deconvolution", "phase", "stitching",
    ]

    def __init__(
        self,
        registry: PluginRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = registry
        self._plugin_tabs: dict[str, _PluginTab] = {}
        self._calibrated: dict[str, bool] = {}

        # Group plugins by umbrella category so the tab title is the
        # umbrella ("Denoising") and the plugin name ("aCNS") shows
        # inside the toggle.
        by_cat: dict[str, list[Any]] = {}
        for plugin in registry.list_all():
            by_cat.setdefault(plugin.category, []).append(plugin)

        ordered_cats = [c for c in self.CATEGORY_ORDER if c in by_cat]
        ordered_cats += [c for c in by_cat if c not in self.CATEGORY_ORDER]

        for cat in ordered_cats:
            plugins = by_cat[cat]
            label = self.CATEGORY_LABELS.get(cat, cat.title())
            for plugin in plugins:
                tab = _PluginTab(plugin, self)
                tab.toggled.connect(
                    lambda active, name=plugin.name: self._on_toggle(name, active),
                )
                tab.run_clicked.connect(
                    lambda name=plugin.name: self._on_run_click(name),
                )
                # When multiple algorithms live under one umbrella (v2),
                # suffix the tab with the algorithm name.
                tab_title = (
                    f"{label} · {plugin.name}" if len(plugins) > 1 else label
                )
                self.addTab(tab, tab_title)
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
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        # Toggle + Run + status on ONE row to keep each tab compact.
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        self._toggle = QCheckBox(f"Apply {plugin.name}")
        self._toggle.setToolTip(
            f"Apply {plugin.name} correction to tiles shown in the viewer. "
            "First check auto-runs calibration."
        )
        self._toggle.toggled.connect(self.toggled.emit)
        top_row.addWidget(self._toggle)

        self._run_button = QPushButton("Run")
        self._run_button.setFixedWidth(60)
        self._run_button.setToolTip(
            f"Run {plugin.name}'s calibration/computation on the current "
            "selection (or all FOVs if nothing selected).",
        )
        self._run_button.clicked.connect(self.run_clicked.emit)
        top_row.addWidget(self._run_button)

        self._status_label = QLabel("Not calibrated")
        self._status_label.setStyleSheet("color: #888888; font-size: 12px;")
        top_row.addWidget(self._status_label, stretch=1)
        layout.addLayout(top_row)

        # Parameter widgets — consult gui_manifest.yaml if present so the
        # absorbed algorithm's original GUI decisions (which params are
        # exposed, with what defaults/ranges) carry over automatically.
        manifest = self._load_manifest_for_plugin(plugin)
        self._hidden_defaults: dict[str, object] = {}
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(4)
        # Wrap long rows: when the label + widget don't fit the 190-px
        # side column, render the label on its own line above the widget
        # instead of truncating. Keeps params readable without widening
        # the column (which would shrink the canvas).
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        params_cls = plugin.parameters()
        for field_name, field_info in params_cls.model_fields.items():
            annotation = field_info.annotation
            default = field_info.default
            gui_hint = manifest.parameters.get(field_name) if manifest else None

            if gui_hint is not None and gui_hint.default is not None:
                default = gui_hint.default

            # Skip (but remember) parameters the manifest hides.
            if gui_hint is not None and not gui_hint.visible:
                self._hidden_defaults[field_name] = default
                continue

            widget: QWidget
            tooltip = (
                gui_hint.tooltip if gui_hint and gui_hint.tooltip
                else (field_info.description or field_name)
            )

            if annotation is float:
                spin = QDoubleSpinBox()
                lo = gui_hint.min if gui_hint and gui_hint.min is not None else -1e6
                hi = gui_hint.max if gui_hint and gui_hint.max is not None else 1e6
                spin.setRange(lo, hi)
                spin.setDecimals(3)
                if gui_hint and gui_hint.step is not None:
                    spin.setSingleStep(gui_hint.step)
                if isinstance(default, (int, float)):
                    spin.setValue(float(default))
                spin.setToolTip(tooltip)
                widget = spin
            elif annotation is int:
                spin_int = QSpinBox()
                lo_i = int(gui_hint.min) if gui_hint and gui_hint.min is not None else 0
                hi_i = int(gui_hint.max) if gui_hint and gui_hint.max is not None else 100000
                spin_int.setRange(lo_i, hi_i)
                if gui_hint and gui_hint.step is not None:
                    spin_int.setSingleStep(int(gui_hint.step))
                if isinstance(default, int):
                    spin_int.setValue(default)
                spin_int.setToolTip(tooltip)
                widget = spin_int
            else:
                continue

            self._param_widgets[field_name] = widget
            form.addRow(field_name, widget)
        layout.addLayout(form)

        if manifest and manifest.notes:
            notes_label = QLabel(manifest.notes)
            notes_label.setWordWrap(True)
            notes_label.setStyleSheet("color: #888888; font-size: 11px;")
            layout.addWidget(notes_label)

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
        params: dict[str, Any] = dict(self._hidden_defaults)
        for name, widget in self._param_widgets.items():
            if isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                params[name] = widget.value()
        return params

    @staticmethod
    def _load_manifest_for_plugin(plugin: ProcessingPlugin):  # type: ignore[no-untyped-def]
        """Look up gui_manifest.yaml next to the plugin's module file."""
        import inspect

        from squid_tools.core.gui_manifest import load_manifest

        try:
            module_file = inspect.getfile(plugin.__class__)
        except (TypeError, OSError):
            return None
        try:
            return load_manifest(module_file)
        except Exception:
            return None
