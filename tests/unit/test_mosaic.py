# tests/unit/test_mosaic.py
from pathlib import Path

from squid_tools.core.data_model import (
    Acquisition,
    AcquisitionChannel,
    AcquisitionFormat,
    AcquisitionMode,
    FOVPosition,
    ObjectiveMetadata,
    OpticalMetadata,
    Region,
    ScanConfig,
)
from squid_tools.gui.mosaic import (
    MosaicAssembler,
    compute_fov_border_rectangles,
    compute_tile_positions,
)


def _make_acquisition_with_grid() -> Acquisition:
    """Create an acquisition with a 3x3 grid of FOVs."""
    pixel_size_um = 0.1725
    tile_size_px = 256
    step_mm = pixel_size_um * tile_size_px * 0.85 / 1000  # 15% overlap

    fovs = []
    idx = 0
    for row in range(3):
        for col in range(3):
            fovs.append(FOVPosition(
                fov_index=idx,
                x_mm=10.0 + col * step_mm,
                y_mm=20.0 + row * step_mm,
            ))
            idx += 1

    return Acquisition(
        path=Path("/tmp/test"),
        format=AcquisitionFormat.INDIVIDUAL_IMAGES,
        mode=AcquisitionMode.WELLPLATE,
        objective=ObjectiveMetadata(
            name="20x", magnification=20.0, numerical_aperture=0.75,
            tube_lens_f_mm=200.0, sensor_pixel_size_um=3.45,
            camera_binning=1, tube_lens_mm=200.0,
        ),
        optical=OpticalMetadata(
            modality="widefield", immersion_medium="air", immersion_ri=1.0,
            numerical_aperture=0.75, pixel_size_um=pixel_size_um,
        ),
        channels=[AcquisitionChannel(
            name="DAPI", illumination_source="LED_405",
            illumination_intensity=50.0, exposure_time_ms=100.0,
        )],
        scan=ScanConfig(
            acquisition_pattern="S-Pattern", fov_pattern="Unidirectional",
            overlap_percent=15.0,
        ),
        regions={"A1": Region(
            region_id="A1", center_mm=(10.0, 20.0, 0.0), shape="Square",
            fovs=fovs,
        )},
    )


def test_compute_tile_positions():
    acq = _make_acquisition_with_grid()
    region = acq.regions["A1"]
    positions = compute_tile_positions(region, acq.objective.pixel_size_um, (256, 256))
    assert len(positions) == 9
    # Each position has translate_yx in pixels
    for pos in positions:
        assert "translate_yx" in pos
        assert "fov_index" in pos
        assert len(pos["translate_yx"]) == 2


def test_tile_positions_are_distinct():
    acq = _make_acquisition_with_grid()
    region = acq.regions["A1"]
    positions = compute_tile_positions(region, acq.objective.pixel_size_um, (256, 256))
    yx_set = {pos["translate_yx"] for pos in positions}
    assert len(yx_set) == 9  # all unique positions


def test_compute_fov_border_rectangles():
    acq = _make_acquisition_with_grid()
    region = acq.regions["A1"]
    positions = compute_tile_positions(region, acq.objective.pixel_size_um, (256, 256))
    borders = compute_fov_border_rectangles(positions, (256, 256))
    assert borders.shape == (9, 4, 2)  # 9 FOVs, 4 corners each, (y, x)


def test_border_rectangles_have_correct_size():
    positions = [{"fov_index": 0, "translate_yx": (0.0, 0.0), "x_mm": 0, "y_mm": 0}]
    borders = compute_fov_border_rectangles(positions, (256, 256))
    rect = borders[0]
    # Width and height should be 256 pixels
    assert rect[1, 1] - rect[0, 1] == 256  # width
    assert rect[2, 0] - rect[0, 0] == 256  # height


def test_empty_region_borders():
    positions = []
    borders = compute_fov_border_rectangles(positions, (256, 256))
    assert borders.shape == (0, 4, 2)


def test_mosaic_assembler():
    acq = _make_acquisition_with_grid()
    assembler = MosaicAssembler(acq, "A1")
    assert assembler.fov_count() == 9
    positions = assembler.tile_positions()
    assert len(positions) == 9
    borders = assembler.border_rectangles()
    assert borders.shape[0] == 9
