# squid_tools/gui/embed.py
"""Embeddable widget for Squid integration.

Exports SquidToolsWidget(parent) that Squid can drop into its dock layout,
identical to the current NDViewerTab integration pattern.
"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from squid_tools.core.data_model import Acquisition
from squid_tools.core.readers import open_acquisition
from squid_tools.core.registry import discover_plugins
from squid_tools.gui.log_panel import LogPanel
from squid_tools.gui.processing_tabs import ProcessingTabs
from squid_tools.gui.wellplate import RegionSelector


class SquidToolsWidget(QWidget):
    """Embeddable squid-tools widget for Squid's dock layout.

    Usage in Squid:
        from squid_tools.gui.embed import SquidToolsWidget
        widget = SquidToolsWidget(parent=self)
        dock.addWidget(widget)
        widget.open(Path("/path/to/acquisition"))
    """

    status_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Processing tabs
        self._tabs = ProcessingTabs()
        self._load_plugins()
        layout.addWidget(self._tabs)

        # Region selector
        self._region_selector = RegionSelector()
        layout.addWidget(self._region_selector)

        # Log
        self._log = LogPanel()
        layout.addWidget(self._log)

        # State
        self._acquisition: Acquisition | None = None

        # Connections
        self._region_selector.region_selected.connect(self._on_region_selected)
        self._tabs.run_requested.connect(self._on_run_plugin)

    def open(self, path: Path) -> None:
        """Open a Squid acquisition directory."""
        try:
            self._acquisition = open_acquisition(path)
            self._region_selector.set_acquisition(self._acquisition)
            msg = (
                f"Opened: {self._acquisition.path.name} "
                f"({self._acquisition.format.value}, "
                f"{len(self._acquisition.regions)} regions)"
            )
            self._log.set_status(msg)
            self.status_changed.emit(msg)
        except Exception as e:
            self._log.set_status(f"Error: {e}")
            self.status_changed.emit(f"Error: {e}")

    def _load_plugins(self) -> None:
        plugins = discover_plugins()
        for plugin in plugins.values():
            self._tabs.add_plugin(plugin)

    def _on_region_selected(self, region_id: str) -> None:
        self._log.set_status(f"Region: {region_id}")

    def _on_run_plugin(self, plugin_name: str, params) -> None:
        self._log.set_status(f"Running {plugin_name}...")
