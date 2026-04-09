"""Single FOV viewer wrapping ndviewer_light's LightweightViewer.

ndviewer_light provides the production-grade 5D viewer with lazy loading,
memory-bounded caching, and channel navigation. This module embeds it
as a QWidget for use in the squid-tools GUI.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from squid_tools.core.data_model import Acquisition

if TYPE_CHECKING:
    from PyQt5.QtWidgets import QWidget

logger = logging.getLogger(__name__)


class SingleFOVWidget:
    """Single FOV viewer using ndviewer_light's LightweightViewer.

    Falls back to a simple napari viewer if ndviewer_light is not installed.
    Access the embeddable Qt widget via :attr:`widget`.
    """

    def __init__(self) -> None:
        self._viewer: object = None
        self._qt_widget: QWidget | None = None
        self._use_ndviewer = False
        self._init_viewer()

    def _init_viewer(self) -> None:
        try:
            from ndviewer_light.core import LightweightViewer

            self._viewer = LightweightViewer()
            self._qt_widget = self._viewer  # LightweightViewer IS a QWidget
            self._use_ndviewer = True
            logger.info("Using ndviewer_light LightweightViewer")
        except ImportError:
            logger.warning("ndviewer_light not installed, falling back to napari")
            import napari

            viewer = napari.Viewer(show=False)
            self._viewer = viewer
            self._qt_widget = viewer.window._qt_window
            self._use_ndviewer = False

    @property
    def widget(self) -> QWidget:
        assert self._qt_widget is not None
        return self._qt_widget

    def set_acquisition(
        self,
        acq: Acquisition,
        region_id: str,
        fov_index: int = 0,
    ) -> None:
        """Load the acquisition dataset into the viewer."""
        if self._use_ndviewer:
            self._viewer.load_dataset(str(acq.path))  # type: ignore[union-attr]
        else:
            self._load_napari_fallback(acq, region_id, fov_index)

    def set_fov(self, fov_index: int) -> None:
        """Navigate to a specific FOV."""
        if self._use_ndviewer:
            self._viewer.load_fov(fov_index)  # type: ignore[union-attr]

    def _load_napari_fallback(
        self, acq: Acquisition, region_id: str, fov_index: int
    ) -> None:
        """Fallback: load channels via napari when ndviewer_light is unavailable."""
        import dask
        import dask.array as da

        from squid_tools.gui.mosaic import _probe_tile_shape_dtype, _read_frame_for_acq

        viewer = self._viewer
        viewer.layers.clear()  # type: ignore[union-attr]

        tile_shape, tile_dtype = _probe_tile_shape_dtype(acq, region_id)
        colormaps = ["gray", "green", "magenta", "cyan", "yellow", "red"]

        for ch_idx, ch in enumerate(acq.channels):
            delayed = dask.delayed(_read_frame_for_acq)(
                acq, region_id, fov_index, ch_idx
            )
            arr = da.from_delayed(delayed, shape=tile_shape, dtype=tile_dtype)
            viewer.add_image(  # type: ignore[union-attr]
                arr,
                name=ch.name,
                colormap=colormaps[ch_idx % len(colormaps)],
                blending="additive",
                visible=True,
            )

        viewer.reset_view()  # type: ignore[union-attr]
