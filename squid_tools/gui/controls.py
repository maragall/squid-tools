"""Left controls panel: border overlay, layer controls."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget


class ControlsPanel(QWidget):
    """Left panel with border overlay and layer controls."""

    borders_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        layout.addWidget(QLabel("Overlay"))
        self.borders_checkbox = QCheckBox("Show FOV Borders")
        self.borders_checkbox.setToolTip("Show/hide FOV border rectangles")
        self.borders_checkbox.setChecked(False)
        self.borders_checkbox.toggled.connect(self.borders_toggled.emit)
        layout.addWidget(self.borders_checkbox)

        layout.addStretch()
