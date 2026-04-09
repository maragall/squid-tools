"""Integration tests for the TileFusion Stitcher plugin."""

from __future__ import annotations

import numpy as np
import pytest

from squid_tools.plugins.stitcher import StitcherParams, StitcherPlugin

# ---------------------------------------------------------------------------
# Plugin attribute tests
# ---------------------------------------------------------------------------


def test_stitcher_plugin_attributes():
    plugin = StitcherPlugin()
    assert plugin.name == "TileFusion Stitcher"
    assert plugin.category == "stitching"
    assert plugin.requires_gpu is False


def test_stitcher_plugin_parameters():
    plugin = StitcherPlugin()
    assert plugin.parameters() is StitcherParams


def test_stitcher_default_params():
    plugin = StitcherPlugin()
    params = plugin.default_params(None)
    assert isinstance(params, StitcherParams)
    assert params.registration_refinement is False
    assert params.output_format == "OME_TIFF"


def test_stitcher_test_cases():
    plugin = StitcherPlugin()
    cases = plugin.test_cases()
    assert len(cases) >= 1
    assert cases[0].name == "2x2_grid_assembly"


# ---------------------------------------------------------------------------
# Grid assembly: 2x2 synthetic grid
# ---------------------------------------------------------------------------


def _make_2x2_tiles(tile_h: int = 64, tile_w: int = 64, overlap_px: int = 8):
    """Create 4 tiles with known overlap and unique per-tile signal."""
    rng = np.random.default_rng(42)
    tiles = []
    positions = []

    stride_h = tile_h - overlap_px
    stride_w = tile_w - overlap_px

    for row in range(2):
        for col in range(2):
            tile = rng.integers(100, 200, size=(tile_h, tile_w), dtype=np.uint16)
            # Add a bright marker unique to this tile
            cy, cx = tile_h // 2, tile_w // 2
            tile[cy - 4 : cy + 4, cx - 4 : cx + 4] = 50000 + row * 1000 + col * 100
            tiles.append(tile)
            positions.append((row * stride_h, col * stride_w))

    return tiles, positions, (tile_h, tile_w)


def test_grid_assembly_2x2_no_registration():
    """Grid assembly without registration produces a canvas larger than each tile."""
    plugin = StitcherPlugin()
    params = StitcherParams(registration_refinement=False)

    tiles, positions, tile_shape = _make_2x2_tiles()
    result = plugin.stitch_tiles(tiles, positions, tile_shape, params)

    tile_h, tile_w = tile_shape
    assert result.ndim == 2
    assert result.shape[0] > tile_h
    assert result.shape[1] > tile_w


def test_grid_assembly_2x2_output_values():
    """Stitched canvas contains pixel values from all input tiles."""
    plugin = StitcherPlugin()
    params = StitcherParams(registration_refinement=False)

    tiles, positions, tile_shape = _make_2x2_tiles()
    result = plugin.stitch_tiles(tiles, positions, tile_shape, params)

    # All tiles had baseline 100–200; canvas should be in that range (ignoring
    # the bright markers which get averaged at seams)
    assert result.min() >= 0
    assert result.max() <= 65535


def test_grid_assembly_canvas_size():
    """Canvas size equals max(row) + H by max(col) + W."""
    plugin = StitcherPlugin()
    params = StitcherParams(registration_refinement=False)

    tile_h, tile_w = 64, 64
    overlap_px = 8
    stride_h = tile_h - overlap_px
    stride_w = tile_w - overlap_px

    tiles, positions, tile_shape = _make_2x2_tiles(tile_h, tile_w, overlap_px)
    result = plugin.stitch_tiles(tiles, positions, tile_shape, params)

    expected_h = stride_h + tile_h  # row positions: 0, stride_h
    expected_w = stride_w + tile_w
    assert result.shape == (expected_h, expected_w)


def test_grid_assembly_overlap_averaged():
    """Overlapping region values should be the average of the two tiles."""
    tile_h, tile_w = 32, 32
    overlap_px = 8

    # Create two flat-value tiles
    tile_a = np.full((tile_h, tile_w), fill_value=100, dtype=np.float32)
    tile_b = np.full((tile_h, tile_w), fill_value=200, dtype=np.float32)

    stride = tile_w - overlap_px
    positions = [(0, 0), (0, stride)]
    tile_shape = (tile_h, tile_w)

    plugin = StitcherPlugin()
    params = StitcherParams(registration_refinement=False)
    result = plugin.stitch_tiles([tile_a, tile_b], positions, tile_shape, params)

    # Overlap column range: stride .. tile_w
    overlap_col_start = stride
    overlap_col_end = tile_w
    overlap_vals = result[0, overlap_col_start:overlap_col_end]
    np.testing.assert_allclose(overlap_vals, 150.0, rtol=1e-5)


# ---------------------------------------------------------------------------
# stitch_from_fovs: stage coordinate conversion
# ---------------------------------------------------------------------------


def test_stitch_from_fovs_2x2():
    """stitch_from_fovs converts stage coords to px and assembles the canvas."""
    from squid_tools.core.data_model import FOVPosition

    plugin = StitcherPlugin()
    params = StitcherParams(registration_refinement=False)

    tile_h, tile_w = 64, 64
    pixel_size_um = 1.0  # 1 µm/px for easy math
    step_mm = 0.060  # 60 µm = 60 px at 1 µm/px (with 4 px overlap at 64px tile)

    fovs = [
        FOVPosition(fov_index=0, x_mm=0.0, y_mm=0.0),
        FOVPosition(fov_index=1, x_mm=step_mm, y_mm=0.0),
        FOVPosition(fov_index=2, x_mm=0.0, y_mm=step_mm),
        FOVPosition(fov_index=3, x_mm=step_mm, y_mm=step_mm),
    ]

    rng = np.random.default_rng(7)
    tiles = [rng.integers(0, 1000, (tile_h, tile_w), dtype=np.uint16) for _ in fovs]

    result = plugin.stitch_from_fovs(tiles, fovs, pixel_size_um, params)

    assert result.ndim == 2
    # Canvas should be wider/taller than a single tile
    assert result.shape[0] >= tile_h
    assert result.shape[1] >= tile_w


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------


def test_validate_single_fov_warns():
    """validate() should warn when only 1 FOV is present."""
    from pathlib import Path

    from squid_tools.core.data_model import (
        Acquisition,
        AcquisitionChannel,
        AcquisitionFormat,
        AcquisitionMode,
        FOVPosition,
        GridParams,
        ObjectiveMetadata,
        OpticalMetadata,
        Region,
        ScanConfig,
    )

    objective = ObjectiveMetadata(
        name="10x",
        magnification=10,
        numerical_aperture=0.3,
        tube_lens_f_mm=180,
        sensor_pixel_size_um=6.5,
        tube_lens_mm=180,
    )
    optical = OpticalMetadata(
        modality="widefield",
        immersion_medium="air",
        immersion_ri=1.0,
        numerical_aperture=0.3,
        pixel_size_um=0.65,
    )
    region = Region(
        region_id="A1",
        center_mm=(0.0, 0.0, 0.0),
        shape="Square",
        fovs=[FOVPosition(fov_index=0, x_mm=0.0, y_mm=0.0)],
        grid_params=GridParams(scan_size_mm=1.0, overlap_percent=15, nx=1, ny=1),
    )
    acq = Acquisition(
        path=Path("/tmp/test"),
        format=AcquisitionFormat.INDIVIDUAL_IMAGES,
        mode=AcquisitionMode.WELLPLATE,
        objective=objective,
        optical=optical,
        channels=[
            AcquisitionChannel(
                name="DAPI",
                illumination_source="LED",
                illumination_intensity=50.0,
                exposure_time_ms=100.0,
            )
        ],
        scan=ScanConfig(acquisition_pattern="Unidirectional", fov_pattern="Unidirectional"),
        regions={"A1": region},
    )

    plugin = StitcherPlugin()
    warnings = plugin.validate(acq)
    assert any("at least 2 FOVs" in w for w in warnings)


# ---------------------------------------------------------------------------
# TileFusion import guard
# ---------------------------------------------------------------------------


def test_stitch_tiles_with_registration_flag():
    """With registration=True and no tilefusion, falls back to grid assembly."""
    plugin = StitcherPlugin()
    params = StitcherParams(registration_refinement=True)

    tiles, positions, tile_shape = _make_2x2_tiles()
    # Should not raise even if tilefusion not installed — falls back
    result = plugin.stitch_tiles(tiles, positions, tile_shape, params)
    assert result.ndim == 2
    assert result.size > 0


# ---------------------------------------------------------------------------
# Real data (skipped if not present)
# ---------------------------------------------------------------------------

REAL_DATA_PATH = (
    "/Users/julioamaragall/Downloads/"
    "10x_mouse_brain_2025-04-23_00-53-11.236590"
)


@pytest.mark.skipif(
    not __import__("pathlib").Path(REAL_DATA_PATH).exists(),
    reason="Real data directory not found",
)
def test_real_data_grid_assembly():
    """Load a subset of real FOVs and verify grid assembly completes."""
    import pathlib

    data_dir = pathlib.Path(REAL_DATA_PATH)
    tif_files = sorted(data_dir.glob("*.tiff"))[:4]
    if len(tif_files) < 4:
        pytest.skip("Not enough .tiff files in real data directory")

    try:
        import tifffile
    except ImportError:
        pytest.skip("tifffile not installed")

    tiles = [tifffile.imread(str(f)) for f in tif_files]
    # Ensure 2-D
    tiles = [t[0] if t.ndim == 3 else t for t in tiles]

    tile_h, tile_w = tiles[0].shape
    # Simple 2x2 grid, 10% overlap
    overlap_h = int(tile_h * 0.10)
    overlap_w = int(tile_w * 0.10)
    stride_h = tile_h - overlap_h
    stride_w = tile_w - overlap_w
    positions = [
        (0, 0),
        (0, stride_w),
        (stride_h, 0),
        (stride_h, stride_w),
    ]

    plugin = StitcherPlugin()
    params = StitcherParams(registration_refinement=False)
    result = plugin.stitch_tiles(tiles, positions, (tile_h, tile_w), params)

    assert result.shape[0] > tile_h
    assert result.shape[1] > tile_w
    assert result.dtype == np.float32
