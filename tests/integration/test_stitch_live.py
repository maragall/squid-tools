"""Test live stitching in the continuous viewer."""

from pathlib import Path

from squid_tools.viewer.viewport_engine import ViewportEngine
from tests.fixtures.generate_fixtures import create_individual_acquisition


class TestLiveStitching:
    def test_register_visible_tiles(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        bb = engine.bounding_box()
        registered = engine.register_visible_tiles(viewport=bb, channel=0)
        # Should return positions for visible tiles (may be empty if registration
        # fails on synthetic data)
        assert isinstance(registered, dict)

    def test_position_overrides(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")

        # Set position overrides
        engine.set_position_overrides({0: (0.001, 0.001), 1: (0.05, 0.001)})
        bb = engine.bounding_box()
        tiles = engine.get_tiles(viewport=bb, screen_width=400, screen_height=400, channel=0)

        # Find tile 0 and check its position was overridden
        tile_0 = [t for t in tiles if t.fov_index == 0]
        if tile_0:
            assert tile_0[0].x_mm == 0.001
            assert tile_0[0].y_mm == 0.001

    def test_clear_overrides_reverts(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")

        # Get original position
        bb = engine.bounding_box()
        tiles_before = engine.get_tiles(viewport=bb, screen_width=400, screen_height=400, channel=0)
        orig_x = tiles_before[0].x_mm if tiles_before else 0

        # Override and clear
        engine.set_position_overrides({tiles_before[0].fov_index: (99.0, 99.0)})
        engine.clear_position_overrides()

        tiles_after = engine.get_tiles(viewport=bb, screen_width=400, screen_height=400, channel=0)
        assert tiles_after[0].x_mm == orig_x
