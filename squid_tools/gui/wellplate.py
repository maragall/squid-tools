"""Region selector widgets for the Squid-Tools GUI.

Provides:
- WellplateGrid: clickable grid for wellplate wells
- RegionDropdown: combobox for flexible/manual tissue regions
- RegionSelector: stacked container that picks the right widget based on acquisition mode
"""

from __future__ import annotations

import re

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QGridLayout,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from squid_tools.core.data_model import Acquisition, AcquisitionMode


class WellplateGrid(QWidget):
    """Clickable grid of QPushButtons, one per well.

    Well IDs are expected in standard plate notation (e.g. "A1", "B3").
    Unknown well IDs are placed in a single-column overflow at the bottom.
    """

    well_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QGridLayout(self)
        self._layout.setSpacing(2)
        self._buttons: dict[str, QPushButton] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_wells(self, well_ids: list[str]) -> None:
        """Create one button per well and arrange them on the grid."""
        # Clear existing buttons
        for btn in self._buttons.values():
            self._layout.removeWidget(btn)
            btn.deleteLater()
        self._buttons.clear()

        overflow_row = 0
        for well_id in well_ids:
            match = re.fullmatch(r"([A-Za-z]+)(\d+)", well_id)
            if match:
                row = _letter_to_index(match.group(1))
                col = int(match.group(2)) - 1
            else:
                # Place unknown IDs in an overflow column beyond normal plate bounds
                row = overflow_row
                col = 999
                overflow_row += 1

            btn = QPushButton(well_id)
            btn.setCheckable(True)
            btn.setFixedSize(36, 28)
            btn.setToolTip(f"Select well {well_id}")
            btn.clicked.connect(lambda checked, w=well_id: self._on_well_clicked(w))
            self._layout.addWidget(btn, row, col)
            self._buttons[well_id] = btn

    def highlight_well(self, well_id: str) -> None:
        """Check the button for *well_id* and uncheck all others."""
        for wid, btn in self._buttons.items():
            btn.setChecked(wid == well_id)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _on_well_clicked(self, well_id: str) -> None:
        self.highlight_well(well_id)
        self.well_selected.emit(well_id)


def _letter_to_index(letters: str) -> int:
    """Convert column letters to a zero-based row index ('A'->0, 'B'->1, ...)."""
    letters = letters.upper()
    result = 0
    for ch in letters:
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result - 1


class RegionDropdown(QWidget):
    """QComboBox listing tissue region IDs for flexible/manual acquisitions."""

    region_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._combo = QComboBox()
        self._combo.setToolTip("Select a tissue region to display")
        layout.addWidget(self._combo)
        layout.addStretch(1)

        self._combo.currentTextChanged.connect(self._on_text_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_regions(self, region_ids: list[str]) -> None:
        """Populate the combo box with region IDs."""
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItems(region_ids)
        self._combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _on_text_changed(self, text: str) -> None:
        if text:
            self.region_selected.emit(text)


class RegionSelector(QWidget):
    """Fixed-width right panel containing a stacked widget.

    Shows WellplateGrid for WELLPLATE acquisitions,
    RegionDropdown for all other modes.
    """

    region_selected = pyqtSignal(str)

    _FIXED_WIDTH = 200
    _IDX_WELLPLATE = 0
    _IDX_DROPDOWN = 1

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(self._FIXED_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        self._wellplate_grid = WellplateGrid()
        self._region_dropdown = RegionDropdown()

        self._stack.insertWidget(self._IDX_WELLPLATE, self._wellplate_grid)
        self._stack.insertWidget(self._IDX_DROPDOWN, self._region_dropdown)

        # Forward child signals
        self._wellplate_grid.well_selected.connect(self.region_selected)
        self._region_dropdown.region_selected.connect(self.region_selected)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_acquisition(self, acq: Acquisition) -> None:
        """Configure the selector based on the acquisition mode."""
        region_ids = list(acq.regions.keys())

        if acq.mode == AcquisitionMode.WELLPLATE:
            self._wellplate_grid.set_wells(region_ids)
            self._stack.setCurrentIndex(self._IDX_WELLPLATE)
        else:
            self._region_dropdown.set_regions(region_ids)
            self._stack.setCurrentIndex(self._IDX_DROPDOWN)
