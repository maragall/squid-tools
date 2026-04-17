"""Tests for viewport-aware tile loading engine."""

from pathlib import Path

from squid_tools.viewer.viewport_engine import ViewportEngine
from tests.fixtures.generate_fixtures import create_individual_acquisition


class TestViewportEngine:
    def test_instantiate(self) -> None:
        engine = ViewportEngine()
        assert engine is not None

    def test_load_acquisition(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=3, ny=3, nz=1, nc=1, nt=1
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        assert engine.is_loaded()

    def test_get_visible_tiles(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=3, ny=3, nz=1, nc=1, nt=1
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        bb = engine.bounding_box()
        # Request all tiles
        tiles = engine.get_tiles(
            viewport=bb, screen_width=800, screen_height=600,
            channel=0, z=0, timepoint=0,
        )
        assert len(tiles) > 0

    def test_tiles_are_downsampled(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        bb = engine.bounding_box()
        # Request at very small screen size -> heavy downsampling
        tiles = engine.get_tiles(
            viewport=bb, screen_width=100, screen_height=100,
            channel=0, z=0, timepoint=0,
        )
        for tile in tiles:
            # Each tile's data should be smaller than full res (128x128)
            assert tile.data.shape[0] <= 128
            assert tile.data.shape[1] <= 128

    def test_partial_viewport(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=3, ny=3, nz=1, nc=1, nt=1
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        bb = engine.bounding_box()
        # Viewport covering only top-left quarter
        half_x = (bb[0] + bb[2]) / 2
        half_y = (bb[1] + bb[3]) / 2
        tiles = engine.get_tiles(
            viewport=(bb[0], bb[1], half_x, half_y),
            screen_width=400, screen_height=400,
            channel=0, z=0, timepoint=0,
        )
        assert len(tiles) < 9  # fewer than all tiles

    def test_caches_tiles(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        bb = engine.bounding_box()
        t1 = engine.get_tiles(viewport=bb, screen_width=400, screen_height=400, channel=0)
        t2 = engine.get_tiles(viewport=bb, screen_width=400, screen_height=400, channel=0)
        # Same data objects from cache
        assert t1[0].data is t2[0].data

    def test_tile_has_position_and_size(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        bb = engine.bounding_box()
        tiles = engine.get_tiles(viewport=bb, screen_width=400, screen_height=400, channel=0)
        for tile in tiles:
            assert hasattr(tile, "x_mm")
            assert hasattr(tile, "y_mm")
            assert hasattr(tile, "width_mm")
            assert hasattr(tile, "height_mm")
            assert hasattr(tile, "data")
            assert tile.width_mm > 0

    def test_compute_contrast_with_fov_indices(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=3, ny=3, nz=1, nc=1, nt=1
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        # Compute contrast using only a subset of FOV indices
        p1, p99 = engine.compute_contrast(channel=0, fov_indices=[0, 1, 2])
        assert p1 >= 0
        assert p99 > p1

    def test_compute_contrast_no_indices_falls_back(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=3, ny=3, nz=1, nc=1, nt=1
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        # No indices: falls back to first max_samples FOVs
        p1, p99 = engine.compute_contrast(channel=0, fov_indices=None, max_samples=5)
        assert p1 >= 0
        assert p99 > p1

    def test_compute_contrast_empty_indices_returns_default(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        # Empty list: no matching FOVs, should return default
        p1, p99 = engine.compute_contrast(channel=0, fov_indices=[])
        assert p1 == 0.0
        assert p99 == 65535.0


class TestViewportEngineHelpers:
    def test_all_fov_indices(self, tmp_path):
        from squid_tools.viewer.viewport_engine import ViewportEngine
        from tests.fixtures.generate_fixtures import create_individual_acquisition

        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        indices = engine.all_fov_indices()
        assert indices == {0, 1, 2, 3}

    def test_visible_fov_indices_uses_camera(self, tmp_path):
        from squid_tools.viewer.viewport_engine import ViewportEngine
        from tests.fixtures.generate_fixtures import create_individual_acquisition

        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        # Entire bounding box → all 4 FOVs
        bb = engine.bounding_box()
        visible = engine.visible_fov_indices(*bb)
        assert visible == {0, 1, 2, 3}

    def test_get_nominal_positions(self, tmp_path):
        from squid_tools.viewer.viewport_engine import ViewportEngine
        from tests.fixtures.generate_fixtures import create_individual_acquisition

        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        positions = engine.get_nominal_positions({0, 1})
        assert 0 in positions and 1 in positions
        assert isinstance(positions[0], tuple)
        assert len(positions[0]) == 2
