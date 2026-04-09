"""Single FOV viewer with multi-channel overlay.

Displays all channels for a single field of view using an embedded napari
viewer.  Channels are added as separate layers so they can be toggled and
coloured independently.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import dask
import dask.array as da

from squid_tools.core.data_model import Acquisition
from squid_tools.gui.mosaic import _probe_tile_shape_dtype, _read_frame_for_acq

if TYPE_CHECKING:
    from PyQt5.QtWidgets import QWidget

logger = logging.getLogger(__name__)

# Default colormaps for first few channels; cycles if more channels exist
_CHANNEL_COLORMAPS = ["gray", "green", "magenta", "cyan", "yellow", "red"]


class SingleFOVWidget:
    """Single FOV viewer with channel overlay.

    Embeds a ``napari.Viewer`` for displaying all channels of a single
    field of view.  Access the embeddable Qt widget via :attr:`widget`.
    """

    def __init__(self) -> None:
        import napari

        self._viewer = napari.Viewer(show=False)
        self._qt_widget: QWidget = self._viewer.window._qt_window

        self._acq: Acquisition | None = None
        self._region_id: str | None = None
        self._fov_index: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def widget(self) -> QWidget:
        """The Qt widget suitable for embedding in a layout."""
        return self._qt_widget

    def set_acquisition(
        self,
        acq: Acquisition,
        region_id: str,
        fov_index: int = 0,
    ) -> None:
        """Load all channels for a single FOV."""
        self._acq = acq
        self._region_id = region_id
        self._fov_index = fov_index
        self._load_channels()

    def set_fov(self, fov_index: int) -> None:
        """Switch to a different FOV (reloads channels)."""
        if fov_index == self._fov_index:
            return
        self._fov_index = fov_index
        if self._acq is not None and self._region_id is not None:
            self._load_channels()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _load_channels(self) -> None:
        """Clear viewer and add one layer per channel."""
        assert self._acq is not None
        assert self._region_id is not None

        self._viewer.layers.clear()

        tile_shape, tile_dtype = _probe_tile_shape_dtype(self._acq, self._region_id)
        n_channels = len(self._acq.channels)

        for ch_idx in range(n_channels):
            delayed_read = dask.delayed(_read_frame_for_acq)(
                self._acq, self._region_id, self._fov_index, ch_idx,
            )
            dask_arr = da.from_delayed(delayed_read, shape=tile_shape, dtype=tile_dtype)

            ch_name = self._acq.channels[ch_idx].name
            cmap = _CHANNEL_COLORMAPS[ch_idx % len(_CHANNEL_COLORMAPS)]

            self._viewer.add_image(
                dask_arr,
                name=ch_name,
                colormap=cmap,
                blending="additive",
                visible=True,
            )

        self._viewer.reset_view()
