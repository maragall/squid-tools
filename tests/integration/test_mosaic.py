"""Integration tests for mosaic tile assembly and single FOV viewer logic.

These tests exercise the data-loading logic without creating any Qt or napari
widgets, so they can run in headless CI environments.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from squid_tools.core.readers.detect import open_acquisition
from squid_tools.gui.mosaic import (
    TileDescriptor,
    _build_border_rectangles,
    _build_tile_layers,
    _probe_tile_shape_dtype,
    _read_frame_for_acq,
)

# ---------------------------------------------------------------------------
# Real-data tests (skipped when the download isn't present)
# ---------------------------------------------------------------------------

REAL_DATA = Path.home() / "Downloads" / "10x_mouse_brain_2025-04-23_00-53-11.236590"
skip_no_data = pytest.mark.skipif(not REAL_DATA.exists(), reason="Real test data not available")


@skip_no_data
def test_mosaic_creates_tiles():
    """Verify mosaic can load real data and create tile descriptors."""
    acq = open_acquisition(REAL_DATA)
    region_id = next(iter(acq.regions))
    layers = _build_tile_layers(acq, region_id, channel=0)
    assert len(layers) > 0
    assert len(layers) == len(acq.regions[region_id].fovs)
    for tile in layers:
        assert isinstance(tile, TileDescriptor)
        assert tile.shape[0] > 0 and tile.shape[1] > 0


@skip_no_data
def test_mosaic_border_rectangles():
    """Border rectangles match tile count and have correct shape."""
    acq = open_acquisition(REAL_DATA)
    region_id = next(iter(acq.regions))
    tiles = _build_tile_layers(acq, region_id, channel=0)
    rects = _build_border_rectangles(tiles)
    assert len(rects) == len(tiles)
    for rect in rects:
        assert rect.shape == (4, 2)


@skip_no_data
def test_probe_tile_shape_dtype():
    """Probing the first tile returns sane shape and dtype."""
    acq = open_acquisition(REAL_DATA)
    region_id = next(iter(acq.regions))
    shape, dtype = _probe_tile_shape_dtype(acq, region_id)
    assert len(shape) == 2
    assert shape[0] > 100 and shape[1] > 100
    assert dtype == np.uint16


@skip_no_data
def test_read_frame_returns_array():
    """Reading a single frame gives a 2-D uint16 array."""
    acq = open_acquisition(REAL_DATA)
    region_id = next(iter(acq.regions))
    fov_index = acq.regions[region_id].fovs[0].fov_index
    frame = _read_frame_for_acq(acq, region_id, fov_index, channel=0)
    assert isinstance(frame, np.ndarray)
    assert frame.ndim == 2
    assert frame.dtype == np.uint16


# ---------------------------------------------------------------------------
# Synthetic-data tests (always run)
# ---------------------------------------------------------------------------


def test_mosaic_with_synthetic_data(individual_tissue: Path):
    """Mosaic tile assembly works with synthetic fixture data."""
    acq = open_acquisition(individual_tissue)
    region_id = next(iter(acq.regions))
    tiles = _build_tile_layers(acq, region_id, channel=0)
    assert len(tiles) == len(acq.regions[region_id].fovs)
    for tile in tiles:
        assert isinstance(tile, TileDescriptor)
        assert tile.shape == (256, 256)


def test_border_rectangles_synthetic(individual_tissue: Path):
    """Border rectangles are generated correctly for synthetic data."""
    acq = open_acquisition(individual_tissue)
    region_id = next(iter(acq.regions))
    tiles = _build_tile_layers(acq, region_id, channel=0)
    rects = _build_border_rectangles(tiles)
    assert len(rects) == len(tiles)
    for rect in rects:
        assert rect.shape == (4, 2)
        # Each rectangle should have width == 256 and height == 256
        width = rect[1, 1] - rect[0, 1]
        height = rect[2, 0] - rect[1, 0]
        assert abs(width - 256.0) < 1e-6
        assert abs(height - 256.0) < 1e-6


def test_tile_translate_offsets(individual_tissue: Path):
    """Tile translate offsets are computed from mm coordinates."""
    acq = open_acquisition(individual_tissue)
    region_id = next(iter(acq.regions))
    tiles = _build_tile_layers(acq, region_id, channel=0)
    pixel_size_um = acq.objective.pixel_size_um

    for tile in tiles:
        fov = next(f for f in acq.regions[region_id].fovs if f.fov_index == tile.fov_index)
        expected_row = fov.y_mm * 1000.0 / pixel_size_um
        expected_col = fov.x_mm * 1000.0 / pixel_size_um
        assert abs(tile.translate_yx[0] - expected_row) < 1e-6
        assert abs(tile.translate_yx[1] - expected_col) < 1e-6


def test_dask_array_computes(individual_tissue: Path):
    """Dask arrays in tiles can be computed to real numpy arrays."""
    acq = open_acquisition(individual_tissue)
    region_id = next(iter(acq.regions))
    tiles = _build_tile_layers(acq, region_id, channel=0)
    # Compute just the first tile to verify laziness works
    result = tiles[0].dask_data.compute()
    assert isinstance(result, np.ndarray)
    assert result.shape == (256, 256)
    assert result.dtype == np.uint16
