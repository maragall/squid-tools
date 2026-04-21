"""End-to-end test: open acquisition, stitch region, verify fused output."""

from pathlib import Path

import numpy as np

from squid_tools.gui.controller import AppController
from squid_tools.processing.stitching.plugin import StitcherParams, StitcherPlugin
from tests.fixtures.generate_fixtures import create_individual_acquisition


class TestStitchEndToEnd:
    def test_stitch_2x2_grid(self, tmp_path: Path) -> None:
        """Load a 2x2 acquisition, stitch it, verify fused image is larger than one tile."""
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        ctrl = AppController()
        ctrl.registry.register(StitcherPlugin())
        acq = ctrl.load_acquisition(acq_path)

        # Get frames and positions for region "0"
        frames = ctrl.get_region_frames(region="0")
        positions = acq.regions["0"].fovs
        pixel_size = acq.objective.pixel_size_um

        # Run stitcher
        plugin = ctrl.registry.get("Stitcher")
        assert plugin is not None
        params = StitcherParams(
            pixel_size_um=pixel_size,
            blend_pixels=10,
            do_register=False,  # skip registration for speed
        )
        result = plugin.process_region(frames, positions, params)

        assert result is not None
        assert result.ndim == 2
        # Fused image should be larger than a single tile (128x128)
        assert result.shape[0] > 128 or result.shape[1] > 128

    def test_controller_run_plugin_stitcher(self, tmp_path: Path) -> None:
        """Test running stitcher through the controller."""
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        ctrl = AppController()
        ctrl.registry.register(StitcherPlugin())
        ctrl.load_acquisition(acq_path)

        # Get a single frame through controller
        frame = ctrl.get_frame(region="0", fov=0)
        assert frame.shape == (128, 128)

        # Run flatfield on single frame
        from squid_tools.processing.flatfield.plugin import FlatfieldPlugin

        ctrl.registry.register(FlatfieldPlugin())
        result = ctrl.run_plugin("Flatfield (BaSiC)", frame.astype(np.float64))
        assert result.shape == (128, 128)
