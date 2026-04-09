# squid_tools/gui/viewer.py
"""Single FOV viewer wrapping ndviewer_light.

Provides 5D navigation (T, Z, C sliders) for viewing individual FOVs.
Falls back to a simple image display if ndviewer_light is not installed.
"""
from __future__ import annotations

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget


class SingleFOVViewer(QWidget):
    """Single FOV viewer with 5D navigation.

    Wraps ndviewer_light if available, otherwise shows a simple QLabel
    with the image data.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._placeholder = QLabel("No FOV loaded")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet("background-color: #1a1a2e; color: #888;")
        layout.addWidget(self._placeholder)

        self._current_frame: np.ndarray | None = None

    def load_frame(self, frame: np.ndarray) -> None:
        """Display a 2D frame."""
        self._current_frame = frame
        h, w = frame.shape[:2]
        self._placeholder.setText(f"FOV: {w}x{h} {frame.dtype}")

    def clear(self) -> None:
        self._current_frame = None
        self._placeholder.setText("No FOV loaded")
