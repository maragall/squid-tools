"""Mosaic view: napari viewer with coordinate-placed tiles and FOV border overlay.

Assembles FOV tiles at their physical (x_mm, y_mm) coordinates using dask
for lazy loading.  Each tile is added as a separate napari Image layer with
a ``translate`` offset so tiles appear at their real stage positions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import dask
import dask.array as da
import numpy as np

from squid_tools.core.data_model import (
    Acquisition,
    AcquisitionFormat,
    FrameKey,
    Region,
)
from squid_tools.core.readers.individual import IndividualImageReader
from squid_tools.core.readers.ome_tiff import OMETiffReader

if TYPE_CHECKING:
    from PyQt5.QtWidgets import QWidget

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tile descriptor (GUI-independent, testable)
# ---------------------------------------------------------------------------


@dataclass
class TileDescriptor:
    """Metadata for a single mosaic tile, decoupled from napari."""

    fov_index: int
    dask_data: da.Array  # lazy 2-D array (H, W)
    translate_yx: tuple[float, float]  # pixel offset (row, col)
    shape: tuple[int, int]  # (H, W)


# ---------------------------------------------------------------------------
# Public helper: build tile descriptors without any Qt / napari dependency
# ---------------------------------------------------------------------------


def _read_frame_for_acq(
    acq: Acquisition,
    region_id: str,
    fov_index: int,
    channel: int,
    z: int = 0,
    timepoint: int = 0,
) -> np.ndarray:
    """Read a single frame using the appropriate reader for *acq*."""
    key = FrameKey(
        region=region_id,
        fov=fov_index,
        z=z,
        channel=channel,
        timepoint=timepoint,
    )
    if acq.format == AcquisitionFormat.OME_TIFF:
        reader = OMETiffReader()
    else:
        reader = IndividualImageReader()
    return reader.read_frame(acq.path, key)


def _probe_tile_shape_dtype(
    acq: Acquisition,
    region_id: str,
) -> tuple[tuple[int, int], np.dtype]:
    """Read the first tile to discover shape and dtype."""
    region = acq.regions[region_id]
    first_fov = region.fovs[0]
    frame = _read_frame_for_acq(acq, region_id, first_fov.fov_index, channel=0)
    return (frame.shape[0], frame.shape[1]), frame.dtype


def _build_tile_layers(
    acq: Acquisition,
    region_id: str,
    channel: int = 0,
    z: int = 0,
    timepoint: int = 0,
) -> list[TileDescriptor]:
    """Build lazy tile descriptors for every FOV in *region_id*.

    Each tile is a ``dask.array`` that lazily reads the TIFF on demand.
    Pixel offsets are computed from mm coordinates and ``pixel_size_um``.

    Parameters
    ----------
    acq:
        Parsed acquisition metadata.
    region_id:
        Which region to tile.
    channel:
        Channel index to load.
    z:
        Z-slice index.
    timepoint:
        Timepoint index.

    Returns
    -------
    list[TileDescriptor]
        One descriptor per FOV, ready for napari consumption.
    """
    region = acq.regions[region_id]
    pixel_size_um: float = acq.objective.pixel_size_um

    # Probe shape / dtype from the first tile
    tile_shape, tile_dtype = _probe_tile_shape_dtype(acq, region_id)

    # Subtract minimum coordinates so tiles start near (0, 0)
    min_x = min(fov.x_mm for fov in region.fovs)
    min_y = min(fov.y_mm for fov in region.fovs)

    tiles: list[TileDescriptor] = []
    for fov in region.fovs:
        # Build a dask delayed read
        delayed_read = dask.delayed(_read_frame_for_acq)(
            acq, region_id, fov.fov_index, channel, z, timepoint,
        )
        dask_arr = da.from_delayed(
            delayed_read,
            shape=tile_shape,
            dtype=tile_dtype,
        )

        # Convert mm -> um -> pixels for the translate offset (relative)
        # napari uses (row, col) = (y, x)
        row_px = (fov.y_mm - min_y) * 1000.0 / pixel_size_um
        col_px = (fov.x_mm - min_x) * 1000.0 / pixel_size_um

        tiles.append(
            TileDescriptor(
                fov_index=fov.fov_index,
                dask_data=dask_arr,
                translate_yx=(row_px, col_px),
                shape=tile_shape,
            )
        )

    return tiles


def _build_border_rectangles(
    tiles: list[TileDescriptor],
) -> list[np.ndarray]:
    """Return rectangle vertices for FOV borders (napari Shapes format).

    Each rectangle is a (4, 2) array of (row, col) corner coordinates.
    """
    rects: list[np.ndarray] = []
    for tile in tiles:
        r, c = tile.translate_yx
        h, w = tile.shape
        rect = np.array([
            [r, c],
            [r, c + w],
            [r + h, c + w],
            [r + h, c],
        ], dtype=np.float64)
        rects.append(rect)
    return rects


# ---------------------------------------------------------------------------
# Qt / napari widget
# ---------------------------------------------------------------------------


class MosaicWidget:
    """Napari-based mosaic viewer.

    Embeds a ``napari.Viewer`` as a Qt widget and provides methods
    to load tiles from an :class:`Acquisition`.

    The class is intentionally *not* subclassed from QWidget directly
    so that napari's own QMainWindow-based widget can be used.
    Access the embeddable Qt widget via :attr:`widget`.
    """

    def __init__(self) -> None:
        import napari  # noqa: F811 – deferred import to keep module importable without Qt

        self._viewer = napari.Viewer(show=False)
        self._qt_widget: QWidget = self._viewer.window._qt_window

        self._acq: Acquisition | None = None
        self._region_id: str | None = None
        self._channel: int = 0
        self._tiles: list[TileDescriptor] = []
        self._borders_visible: bool = False

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
        channel: int = 0,
    ) -> None:
        """Load tiles for the given region and channel."""
        self._acq = acq
        self._region_id = region_id
        self._channel = channel
        self._load_tiles()

    def set_channel(self, channel: int) -> None:
        """Switch displayed channel (reloads tiles lazily)."""
        if channel == self._channel:
            return
        self._channel = channel
        if self._acq is not None and self._region_id is not None:
            self._load_tiles()

    def show_borders(self, visible: bool) -> None:
        """Toggle FOV border overlay."""
        self._borders_visible = visible
        for layer in self._viewer.layers:
            if layer.name == "FOV Borders":
                layer.visible = visible
                return

    def reset_view(self) -> None:
        """Reset the camera to show all tiles."""
        self._viewer.reset_view()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _load_tiles(self) -> None:
        """Clear viewer and add tile layers + borders."""
        assert self._acq is not None
        assert self._region_id is not None

        self._viewer.layers.clear()

        self._tiles = _build_tile_layers(
            self._acq, self._region_id, channel=self._channel,
        )

        # Determine a shared contrast range for nice defaults
        for _i, tile in enumerate(self._tiles):
            self._viewer.add_image(
                tile.dask_data,
                name=f"FOV_{tile.fov_index:03d}",
                translate=tile.translate_yx,
                blending="translucent",
                visible=True,
            )

        # FOV border overlay
        rects = _build_border_rectangles(self._tiles)
        if rects:
            self._viewer.add_shapes(
                rects,
                shape_type="rectangle",
                name="FOV Borders",
                edge_color="cyan",
                edge_width=2,
                face_color="transparent",
                visible=self._borders_visible,
            )

        self._viewer.reset_view()


# ---------------------------------------------------------------------------
# Coordinate-placement helpers (testable without napari)
# ---------------------------------------------------------------------------


def compute_tile_positions(
    region: Region,
    pixel_size_um: float,
    tile_shape: tuple[int, int],
) -> list[dict[str, Any]]:
    """Compute napari translate transforms for each FOV in a region.

    Converts mm stage coordinates to pixel coordinates for napari placement.

    Returns list of dicts with keys: fov_index, translate_yx (pixels), x_mm, y_mm
    """
    positions = []
    for fov in region.fovs:
        # Convert mm to pixels: mm * 1000 = um, um / pixel_size_um = pixels
        y_px = fov.y_mm * 1000.0 / pixel_size_um
        x_px = fov.x_mm * 1000.0 / pixel_size_um
        positions.append({
            "fov_index": fov.fov_index,
            "translate_yx": (y_px, x_px),
            "x_mm": fov.x_mm,
            "y_mm": fov.y_mm,
        })
    return positions


def compute_fov_border_rectangles(
    positions: list[dict[str, Any]],
    tile_shape: tuple[int, int],
) -> np.ndarray:
    """Compute rectangle vertices for FOV borders.

    Returns array of shape (N, 4, 2) where N is number of FOVs,
    4 is corners (top-left, top-right, bottom-right, bottom-left),
    2 is (y, x) in pixel coordinates.
    """
    h, w = tile_shape
    rectangles = []
    for pos in positions:
        y0, x0 = pos["translate_yx"]
        rect = np.array([
            [y0, x0],          # top-left
            [y0, x0 + w],      # top-right
            [y0 + h, x0 + w],  # bottom-right
            [y0 + h, x0],      # bottom-left
        ])
        rectangles.append(rect)
    return np.array(rectangles) if rectangles else np.empty((0, 4, 2))


class MosaicAssembler:
    """Assembles a mosaic from FOV tiles placed at stage coordinates.

    This is the data layer - it computes positions and creates dask arrays.
    The napari viewer integration happens in add_to_viewer().
    """

    def __init__(self, acquisition: Acquisition, region_id: str) -> None:
        self._acq = acquisition
        self._region = acquisition.regions[region_id]
        self._pixel_size_um = acquisition.objective.pixel_size_um

    @property
    def region(self) -> Region:
        return self._region

    def tile_positions(self, tile_shape: tuple[int, int] = (256, 256)) -> list[dict[str, Any]]:
        return compute_tile_positions(self._region, self._pixel_size_um, tile_shape)

    def border_rectangles(self, tile_shape: tuple[int, int] = (256, 256)) -> np.ndarray:
        positions = self.tile_positions(tile_shape)
        return compute_fov_border_rectangles(positions, tile_shape)

    def add_to_viewer(self, viewer: Any, channel: int = 0, z: int = 0, t: int = 0) -> None:
        """Add mosaic tiles and borders to a napari viewer.

        Each FOV becomes a separate napari Image layer with translate transform.
        Borders are a single Shapes layer.
        """
        import napari  # noqa: F401  # runtime import

        tile_shape = (256, 256)  # default, will be updated from first frame
        borders = self.border_rectangles(tile_shape)

        # Add border overlay
        if len(borders) > 0:
            viewer.add_shapes(
                borders,
                shape_type="rectangle",
                edge_color="white",
                edge_width=2,
                face_color="transparent",
                name=f"FOV Borders ({self._region.region_id})",
            )

    def fov_count(self) -> int:
        return len(self._region.fovs)
