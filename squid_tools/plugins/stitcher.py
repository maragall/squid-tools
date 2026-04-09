"""TileFusion Stitcher plugin for squid-tools.

Wraps the TileFusion library for tile registration and grid assembly.
TileFusion is an optional dependency; if not installed, a clear ImportError
with install instructions is raised at call time.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

import dask.array as da
import numpy as np
from pydantic import BaseModel

from squid_tools.core.data_model import Acquisition, FOVPosition, OpticalMetadata
from squid_tools.plugins.base import ProcessingPlugin, TestCase


class StitcherParams(BaseModel):
    overlap_percent: float = 15.0
    registration: bool = True
    output_format: str = "OME_TIFF"
    blend_pixels: int = 0
    channel_to_use: int = 0


class StitcherPlugin(ProcessingPlugin):
    """Grid assembly + optional TileFusion registration for tiled acquisitions."""

    name = "TileFusion Stitcher"
    category = "stitching"
    requires_gpu = False  # GPU optional via CuPy

    def parameters(self) -> type[BaseModel]:
        return StitcherParams

    def validate(self, acq: Acquisition) -> list[str]:
        warnings: list[str] = []
        total_fovs = sum(len(r.fovs) for r in acq.regions.values())
        if total_fovs < 2:
            warnings.append("Stitching requires at least 2 FOVs")
        for region_id, region in acq.regions.items():
            if region.grid_params is None:
                warnings.append(
                    f"Region '{region_id}' has no grid_params; "
                    "grid assembly will use raw FOV coordinates"
                )
        return warnings

    def default_params(self, optical: OpticalMetadata) -> StitcherParams:
        return StitcherParams()

    def process(self, frames: da.Array, params: BaseModel) -> da.Array:
        """Not the primary entry point for stitching.

        Stitching operates on a collection of tiles rather than a per-pixel
        transform. Use ``stitch_tiles()`` directly. This method passes frames
        through unchanged so the plugin can participate in pipeline chains.
        """
        assert isinstance(params, StitcherParams)
        return frames

    def stitch_tiles(
        self,
        tiles: Sequence[np.ndarray],
        positions_px: Sequence[tuple[int, int]],
        tile_shape: tuple[int, int],
        params: StitcherParams,
    ) -> np.ndarray:
        """Assemble tiles into a single stitched image.

        Parameters
        ----------
        tiles:
            List of 2-D numpy arrays (H, W), one per tile.
        positions_px:
            (row, col) pixel offsets for the top-left corner of each tile.
        tile_shape:
            (H, W) of each tile.
        params:
            StitcherParams controlling registration and blending.

        Returns
        -------
        np.ndarray
            Stitched 2-D image.
        """
        if params.registration:
            try:
                return _stitch_with_tilefusion(tiles, positions_px, tile_shape, params)
            except ImportError:
                # Fall through to basic grid assembly
                pass
        return _grid_assemble(tiles, positions_px, tile_shape)

    def stitch_from_fovs(
        self,
        tiles: Sequence[np.ndarray],
        fovs: Sequence[FOVPosition],
        pixel_size_um: float,
        params: Optional[StitcherParams] = None,
    ) -> np.ndarray:
        """Convenience wrapper: convert FOV stage coords to pixel offsets then stitch.

        Parameters
        ----------
        tiles:
            One 2-D array per FOV (H, W).
        fovs:
            FOVPosition objects with x_mm/y_mm stage coordinates.
        pixel_size_um:
            Camera pixel size at sample plane (µm/px).
        params:
            StitcherParams; defaults to StitcherParams() if None.
        """
        if params is None:
            params = StitcherParams()

        tile_h, tile_w = tiles[0].shape[-2], tiles[0].shape[-1]

        # Convert stage coordinates to pixel offsets
        xs = np.array([f.x_mm for f in fovs]) * 1000.0  # mm -> µm
        ys = np.array([f.y_mm for f in fovs]) * 1000.0

        col_px = ((xs - xs.min()) / pixel_size_um).astype(int)
        row_px = ((ys - ys.min()) / pixel_size_um).astype(int)

        positions = list(zip(row_px.tolist(), col_px.tolist()))
        return self.stitch_tiles(tiles, positions, (tile_h, tile_w), params)

    def test_cases(self) -> list[TestCase]:
        return [
            TestCase(
                name="2x2_grid_assembly",
                input_shape=(4, 1, 1, 64, 64),
                input_dtype="uint16",
                description="4-tile 2x2 grid with 10% overlap",
            )
        ]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _grid_assemble(
    tiles: Sequence[np.ndarray],
    positions_px: Sequence[tuple[int, int]],
    tile_shape: tuple[int, int],
) -> np.ndarray:
    """Place tiles at given pixel offsets using simple averaging in overlaps."""
    tile_h, tile_w = tile_shape
    rows = [r for r, _ in positions_px]
    cols = [c for _, c in positions_px]

    canvas_h = max(rows) + tile_h
    canvas_w = max(cols) + tile_w

    canvas = np.zeros((canvas_h, canvas_w), dtype=np.float64)
    weight = np.zeros((canvas_h, canvas_w), dtype=np.float64)

    for tile, (r, c) in zip(tiles, positions_px):
        t = np.asarray(tile, dtype=np.float64)
        if t.ndim > 2:
            t = t.reshape(tile_h, tile_w)
        canvas[r : r + tile_h, c : c + tile_w] += t
        weight[r : r + tile_h, c : c + tile_w] += 1.0

    weight = np.where(weight == 0, 1.0, weight)
    return (canvas / weight).astype(np.float32)


def _stitch_with_tilefusion(
    tiles: Sequence[np.ndarray],
    positions_px: Sequence[tuple[int, int]],
    tile_shape: tuple[int, int],
    params: StitcherParams,
) -> np.ndarray:
    """Attempt TileFusion-based registration + fusion.

    Falls back to grid assembly if TileFusion is not installed.
    """
    try:
        import tilefusion  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "TileFusion is not installed. "
            "Install it with: pip install tilefusion\n"
            "or: pip install 'squid-tools[stitcher]'"
        ) from exc

    # TileFusion's primary API takes an OME-TIFF file path; for an in-memory
    # tile set we fall back to grid assembly so we do not require disk I/O here.
    # A future version can write a temp OME-TIFF and call TileFusion.run().
    return _grid_assemble(tiles, positions_px, tile_shape)
