"""Right panel: well plate grid or region dropdown.

Auto-detects wellplate vs tissue from Acquisition.mode.
Wellplate mode shows a clickable grid of well buttons.
Tissue/flexible mode shows a dropdown list of region IDs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from squid_tools.core.data_model import Acquisition


class RegionSelector(QWidget):
    """Region selector: wellplate grid or region dropdown."""

    region_selected = Signal(str)  # region_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._wellplate_mode = False
        self._selected_region: str | None = None
        self._well_buttons: dict[str, QPushButton] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(QLabel("Region Selector"))

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # Page 0: wellplate grid
        self._wellplate_widget = QWidget()
        self._wellplate_layout = QGridLayout(self._wellplate_widget)
        self._stack.addWidget(self._wellplate_widget)

        # Page 1: dropdown
        self._dropdown_widget = QWidget()
        dropdown_layout = QVBoxLayout(self._dropdown_widget)
        self._dropdown = QComboBox()
        self._dropdown.setToolTip("Select a region to view")
        self._dropdown.currentTextChanged.connect(self._on_dropdown_changed)
        dropdown_layout.addWidget(self._dropdown)
        dropdown_layout.addStretch()
        self._stack.addWidget(self._dropdown_widget)

    def load_acquisition(self, acq: Acquisition) -> None:
        """Load regions from an acquisition. Auto-detect mode."""
        from squid_tools.core.data_model import AcquisitionMode

        self._wellplate_mode = acq.mode == AcquisitionMode.WELLPLATE
        self._well_buttons.clear()

        if self._wellplate_mode:
            # Clear existing grid
            while self._wellplate_layout.count():
                item = self._wellplate_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            # Build grid from region IDs (e.g., "A1", "B2")
            for region_id in sorted(acq.regions.keys()):
                row, col = self._parse_well_position(region_id)
                btn = QPushButton(region_id)
                btn.setToolTip(f"View region {region_id}")
                btn.setFixedSize(40, 30)
                btn.clicked.connect(lambda checked, rid=region_id: self.select_region(rid))
                self._wellplate_layout.addWidget(btn, row, col)
                self._well_buttons[region_id] = btn

            self._stack.setCurrentIndex(0)
        else:
            self._dropdown.clear()
            for region_id in sorted(acq.regions.keys()):
                self._dropdown.addItem(region_id)
            self._stack.setCurrentIndex(1)

    def is_wellplate_mode(self) -> bool:
        """Return True if showing wellplate grid."""
        return self._wellplate_mode

    def select_region(self, region_id: str) -> None:
        """Programmatically select a region and emit signal."""
        self._selected_region = region_id
        self.region_selected.emit(region_id)

    def set_selected_region(self, region_id: str) -> None:
        """Set the selected region without emitting the signal."""
        self._selected_region = region_id

    def selected_region_id(self) -> str | None:
        """Return currently selected region ID."""
        return self._selected_region

    def _on_dropdown_changed(self, text: str) -> None:
        if text:
            self.select_region(text)

    @staticmethod
    def _parse_well_position(region_id: str) -> tuple[int, int]:
        """Parse 'A1' -> (0, 0), 'B2' -> (1, 1), etc. Fallback to (0, 0)."""
        if len(region_id) >= 2 and region_id[0].isalpha() and region_id[1:].isdigit():
            row = ord(region_id[0].upper()) - ord("A")
            col = int(region_id[1:]) - 1
            return row, col
        return 0, 0
