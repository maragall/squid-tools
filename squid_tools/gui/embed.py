"""Embeddable widget for Squid integration.

SquidToolsWidget can be dropped into Squid's dock layout,
identical to the NDViewerTab integration pattern.
"""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from squid_tools.core.registry import PluginRegistry
from squid_tools.gui.controls import ControlsPanel
from squid_tools.gui.log_panel import LogPanel
from squid_tools.gui.processing_tabs import ProcessingTabs
from squid_tools.gui.region_selector import RegionSelector


class SquidToolsWidget(QWidget):
    """Embeddable squid-tools widget for Squid's dock layout.

    Contains all panels except the window frame. Squid can embed
    this as a tab or dock widget.
    """

    def __init__(
        self, registry: PluginRegistry | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)

        if registry is None:
            registry = PluginRegistry()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.processing_tabs = ProcessingTabs(registry)
        layout.addWidget(self.processing_tabs)

        self.controls_panel = ControlsPanel()
        layout.addWidget(self.controls_panel)

        self.region_selector = RegionSelector()
        layout.addWidget(self.region_selector)

        self.log_panel = LogPanel()
        layout.addWidget(self.log_panel)
