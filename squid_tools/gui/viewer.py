"""Viewer widget wrapping ndviewer_light's LightweightViewer.

ndviewer_light provides the production-grade 5D viewer with lazy loading,
memory-bounded caching, FOV/time/channel navigation, and processing support.
This module embeds it directly as the squid-tools viewer.
"""
from __future__ import annotations

import logging
from pathlib import Path

from squid_tools.core.data_model import Acquisition

logger = logging.getLogger(__name__)


def create_viewer(parent=None):  # type: ignore[no-untyped-def]
    """Create the viewer widget. Returns (widget, is_ndviewer_light)."""
    try:
        from ndviewer_light.core import LightweightViewer

        viewer = LightweightViewer()
        logger.info("Using ndviewer_light LightweightViewer")
        return viewer, True
    except ImportError:
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QLabel

        placeholder = QLabel("ndviewer_light not installed.\npip install ndviewer_light")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("color: #888; font-size: 12pt;")
        logger.warning("ndviewer_light not available")
        return placeholder, False


class ViewerWidget:
    """Wraps ndviewer_light's LightweightViewer as the squid-tools viewer.

    LightweightViewer is a QWidget that handles:
    - Loading acquisitions via load_dataset(path)
    - FOV navigation (slider)
    - Time navigation (slider)
    - Channel composite display
    - Memory-bounded LRU cache
    - TiffFile handle pool (128 max)
    - Dask lazy loading with debouncing
    """

    def __init__(self) -> None:
        self._widget, self._is_ndviewer = create_viewer()
        self._acq: Acquisition | None = None

    @property
    def widget(self):  # type: ignore[no-untyped-def]
        return self._widget

    @property
    def is_ready(self) -> bool:
        return self._is_ndviewer

    def load_acquisition(self, acq: Acquisition) -> None:
        """Load an acquisition into the viewer."""
        self._acq = acq
        if self._is_ndviewer:
            self._widget.load_dataset(str(acq.path))

    def load_fov(self, fov_index: int) -> None:
        """Navigate to a specific FOV."""
        if self._is_ndviewer:
            self._widget.load_fov(fov_index)

    def get_xarray_data(self):  # type: ignore[no-untyped-def]
        """Get the current xarray data for processing."""
        if self._is_ndviewer and hasattr(self._widget, '_xarray_data'):
            return self._widget._xarray_data
        return None
