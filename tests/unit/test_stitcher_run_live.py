"""Tests for StitcherPlugin.run_live().

After Cycle "stitcher: vendor TileFusion" the plugin delegates registration
+ optimization to the vendored TileFusion package. TileFusion expects
Squid's stage-coordinate-named individual-images format
({x_mm}_{y_mm}_{z}_{channel}.tif), which differs from the simplified
{region}_{fov}_{z}_{channel}.tiff convention our synthetic test fixture
produces.

Internals of the registration/optimization pipeline are tested upstream
in `_audit/stitcher/tests/`. Here we only assert the plugin's public
contract: it can be invoked without raising, and on incompatible fixtures
it logs a construction error rather than crashing.
"""

import logging
from pathlib import Path

from squid_tools.processing.stitching.plugin import StitcherParams, StitcherPlugin
from squid_tools.viewer.viewport_engine import ViewportEngine
from tests.fixtures.generate_fixtures import create_individual_acquisition


class TestStitcherRunLive:
    def test_run_live_handles_unsupported_fixture_gracefully(
        self, tmp_path: Path, caplog,
    ) -> None:
        """Synthetic test fixture isn't Squid-shaped; plugin must not crash."""
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = StitcherPlugin()
        params = StitcherParams(pixel_size_um=engine.pixel_size_um)

        caplog.set_level(logging.ERROR, logger="squid_tools.processing.stitching")
        plugin.run_live(
            selection={0, 1, 2, 3}, engine=engine,
            params=params, progress=lambda *_: None,
        )
        # On the synthetic fixture, TileFusion raises FileNotFoundError because
        # it expects {x_mm}_{y_mm}_{z}_{channel}.tif. The plugin must catch and
        # log; engine state must be unchanged.
        errs = [
            r for r in caplog.records
            if r.name.startswith("squid_tools.processing.stitching")
            and r.levelno == logging.ERROR
        ]
        assert errs, "Stitcher should log an error when TileFusion can't load"
        assert engine._position_overrides == {}, (
            "no position overrides should be set on a failed run"
        )
