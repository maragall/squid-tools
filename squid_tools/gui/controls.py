"""Controls panel widget for the Squid-Tools GUI.

Provides view-mode toggles and overlay options in a fixed-width left panel.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGroupBox,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class ControlsPanel(QWidget):
    """Fixed-width left panel with view-mode and overlay controls."""

    view_mode_changed = pyqtSignal(str)   # emits "fov" or "mosaic"
    borders_toggled = pyqtSignal(bool)

    _FIXED_WIDTH = 160

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(self._FIXED_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)

        # ---- View group ----
        view_group = QGroupBox("View")
        view_group.setToolTip("Switch between single field-of-view and mosaic view modes")
        vg_layout = QVBoxLayout(view_group)
        vg_layout.setSpacing(4)

        self._btn_fov = QPushButton("Single FOV")
        self._btn_fov.setCheckable(True)
        self._btn_fov.setChecked(True)
        self._btn_fov.setToolTip("Display a single field of view at full resolution")

        self._btn_mosaic = QPushButton("Mosaic")
        self._btn_mosaic.setCheckable(True)
        self._btn_mosaic.setToolTip("Display all FOVs stitched together as a mosaic")

        # Mutually exclusive
        self._view_group = QButtonGroup(self)
        self._view_group.setExclusive(True)
        self._view_group.addButton(self._btn_fov)
        self._view_group.addButton(self._btn_mosaic)

        vg_layout.addWidget(self._btn_fov)
        vg_layout.addWidget(self._btn_mosaic)
        root.addWidget(view_group)

        # ---- Overlay group ----
        overlay_group = QGroupBox("Overlay")
        overlay_group.setToolTip("Toggle overlays drawn on top of the image viewer")
        og_layout = QVBoxLayout(overlay_group)
        og_layout.setSpacing(4)

        self._chk_borders = QCheckBox("FOV Borders")
        self._chk_borders.setToolTip("Draw bounding boxes around each field of view")
        og_layout.addWidget(self._chk_borders)
        root.addWidget(overlay_group)

        # ---- Layers group ----
        layers_group = QGroupBox("Layers")
        layers_group.setToolTip("Active image layers (populated when an acquisition is loaded)")
        lg_layout = QVBoxLayout(layers_group)
        lg_layout.setSpacing(4)

        self._layers_placeholder = QLabel("No layers")
        self._layers_placeholder.setToolTip(
            "Layers will appear here once an acquisition is opened"
        )
        lg_layout.addWidget(self._layers_placeholder)
        root.addWidget(layers_group)

        root.addStretch(1)

        # ---- Connections ----
        self._btn_fov.toggled.connect(self._on_view_toggled)
        self._btn_mosaic.toggled.connect(self._on_view_toggled)
        self._chk_borders.toggled.connect(self.borders_toggled)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _on_view_toggled(self, checked: bool) -> None:
        if not checked:
            return
        mode = "fov" if self._btn_fov.isChecked() else "mosaic"
        self.view_mode_changed.emit(mode)
