"""Unified viewer: single FOV and mosaic in one napari canvas.

One viewer, one button toggles mode. Colors and contrast are retained
across transitions. Data loading uses memory-bounded caching.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import dask
import dask.array as da
import numpy as np

from squid_tools.core.data_model import Acquisition
from squid_tools.gui.mosaic import (
    _build_border_rectangles,
    _build_tile_layers,
    _probe_tile_shape_dtype,
    _read_frame_for_acq,
)

if TYPE_CHECKING:
    from PyQt5.QtWidgets import QWidget

logger = logging.getLogger(__name__)

_COLORMAPS = ["gray", "green", "magenta", "cyan", "yellow", "red"]


class UnifiedViewer:
    """Single napari viewer that toggles between FOV and mosaic modes.

    Same canvas, same colors, seamless transition.
    """

    def __init__(self) -> None:
        import napari

        self._viewer = napari.Viewer(show=False)
        self._qt_widget: QWidget = self._viewer.window._qt_window

        self._acq: Acquisition | None = None
        self._region_id: str | None = None
        self._fov_index: int = 0
        self._mode: str = "fov"
        self._borders_visible: bool = False

        # Persist contrast/colormap across mode switches
        self._channel_contrast: dict[int, tuple[float, float]] = {}
        self._channel_colormaps: dict[int, str] = {}

    @property
    def widget(self) -> QWidget:
        return self._qt_widget

    def set_acquisition(self, acq: Acquisition, region_id: str) -> None:
        self._acq = acq
        self._region_id = region_id
        self._fov_index = 0
        self._refresh()

    def set_mode(self, mode: str) -> None:
        if mode == self._mode:
            return
        self._save_contrast()
        self._mode = mode
        self._refresh()

    def set_fov(self, fov_index: int) -> None:
        self._fov_index = fov_index
        if self._mode == "fov":
            self._save_contrast()
            self._refresh()

    def show_borders(self, visible: bool) -> None:
        self._borders_visible = visible
        for layer in self._viewer.layers:
            if layer.name == "FOV Borders":
                layer.visible = visible
                return

    def _save_contrast(self) -> None:
        for layer in self._viewer.layers:
            if hasattr(layer, "contrast_limits") and layer.name != "FOV Borders":
                try:
                    idx = int(layer.metadata.get("ch_idx", -1))
                    if idx >= 0:
                        self._channel_contrast[idx] = tuple(layer.contrast_limits)
                        self._channel_colormaps[idx] = str(layer.colormap.name)
                except (ValueError, AttributeError):
                    pass

    def _refresh(self) -> None:
        if self._acq is None or self._region_id is None:
            return

        self._viewer.layers.clear()

        if self._mode == "fov":
            self._load_fov()
        else:
            self._load_mosaic()

        self._viewer.reset_view()

    def _load_fov(self) -> None:
        acq = self._acq
        assert acq is not None
        region_id = self._region_id
        assert region_id is not None

        tile_shape, tile_dtype = _probe_tile_shape_dtype(acq, region_id)

        for ch_idx, ch in enumerate(acq.channels):
            delayed = dask.delayed(_read_frame_for_acq)(
                acq, region_id, self._fov_index, ch_idx
            )
            arr = da.from_delayed(delayed, shape=tile_shape, dtype=tile_dtype)

            cmap = self._channel_colormaps.get(ch_idx, _COLORMAPS[ch_idx % len(_COLORMAPS)])
            layer = self._viewer.add_image(
                arr,
                name=ch.name,
                colormap=cmap,
                blending="additive",
                visible=True,
                metadata={"ch_idx": ch_idx},
            )
            if ch_idx in self._channel_contrast:
                layer.contrast_limits = self._channel_contrast[ch_idx]

    def _load_mosaic(self) -> None:
        acq = self._acq
        assert acq is not None
        region_id = self._region_id
        assert region_id is not None

        # Load channel 0 mosaic (most common use)
        tiles = _build_tile_layers(acq, region_id, channel=0)

        for tile in tiles:
            layer = self._viewer.add_image(
                tile.dask_data,
                name=f"FOV_{tile.fov_index:03d}",
                translate=tile.translate_yx,
                blending="translucent",
                visible=True,
                metadata={"ch_idx": 0},
            )
            if 0 in self._channel_contrast:
                layer.contrast_limits = self._channel_contrast[0]

        rects = _build_border_rectangles(tiles)
        if rects:
            self._viewer.add_shapes(
                rects,
                shape_type="rectangle",
                name="FOV Borders",
                edge_color="white",
                edge_width=2,
                face_color="transparent",
                visible=self._borders_visible,
            )
