"""Tests for stitcher plugin wrapper."""


import numpy as np

from squid_tools.core.data_model import (
    Acquisition,
    AcquisitionFormat,
    AcquisitionMode,
    FOVPosition,
    ObjectiveMetadata,
    OpticalMetadata,
)
from squid_tools.processing.stitching.plugin import StitcherParams, StitcherPlugin


class TestStitcherPlugin:
    def test_instantiate(self) -> None:
        plugin = StitcherPlugin()
        assert plugin.name == "Stitcher"
        assert plugin.category == "stitching"

    def test_parameters(self) -> None:
        plugin = StitcherPlugin()
        assert plugin.parameters() is StitcherParams

    def test_process_region_returns_fused(self) -> None:
        """Stitch a 2x1 grid with known overlap."""
        plugin = StitcherPlugin()
        h, w = 64, 64
        tile1 = np.random.rand(h, w).astype(np.float32)
        tile2 = np.random.rand(h, w).astype(np.float32)
        frames = {0: tile1, 1: tile2}
        positions = [
            FOVPosition(fov_index=0, x_mm=0.0, y_mm=0.0),
            FOVPosition(fov_index=1, x_mm=0.05, y_mm=0.0),  # ~50px offset at 1um/px
        ]
        params = StitcherParams(
            pixel_size_um=1.0,
            blend_pixels=10,
            do_register=False,  # skip registration, just fuse at nominal positions
        )
        result = plugin.process_region(frames, positions, params)
        assert result is not None
        assert result.ndim == 2
        # Fused image should be wider than a single tile
        assert result.shape[1] > w

    def test_process_single_frame_passthrough(self) -> None:
        """process() on a single frame should return it unchanged."""
        plugin = StitcherPlugin()
        frame = np.random.rand(64, 64).astype(np.float32)
        result = plugin.process(frame, StitcherParams(pixel_size_um=1.0))
        assert np.array_equal(result, frame)

    def test_validate_empty(self) -> None:
        plugin = StitcherPlugin()
        acq = Acquisition(
            path="/tmp/test",
            format=AcquisitionFormat.INDIVIDUAL_IMAGES,
            mode=AcquisitionMode.WELLPLATE,
            objective=ObjectiveMetadata(name="20x", magnification=20.0, pixel_size_um=0.325),
        )
        assert plugin.validate(acq) == []

    def test_default_params(self) -> None:
        plugin = StitcherPlugin()
        params = plugin.default_params(OpticalMetadata(pixel_size_um=0.325))
        assert isinstance(params, StitcherParams)
        assert params.pixel_size_um == 0.325

    def test_test_cases(self) -> None:
        plugin = StitcherPlugin()
        cases = plugin.test_cases()
        assert len(cases) > 0
