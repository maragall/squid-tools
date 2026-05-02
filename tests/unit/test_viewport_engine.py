"""Tests for viewport-aware tile loading engine."""

import logging
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


class TestViewportEngineLogging:
    def test_load_emits_debug_log(self, individual_acquisition, caplog):
        from squid_tools.viewer.viewport_engine import ViewportEngine

        caplog.set_level(logging.DEBUG, logger="squid_tools")
        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        debugs = [
            r for r in caplog.records
            if r.name.startswith("squid_tools.viewer.viewport_engine")
            and r.levelno == logging.DEBUG
        ]
        assert debugs, "engine.load should emit at least one DEBUG log"


class TestViewportEnginePyramidCache:
    def test_get_pyramid_level_zero_returns_raw(
        self, individual_acquisition,
    ) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        frame = engine._get_pyramid(fov=0, z=0, channel=0, timepoint=0, level=0)
        assert frame.ndim in (2, 3)
        assert (0, 0, 0, 0, 0) not in engine._pyramid_cache

    def test_get_pyramid_level_one_caches_and_halves(
        self, individual_acquisition,
    ) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        raw = engine._load_raw(fov=0, z=0, channel=0, timepoint=0)
        level1 = engine._get_pyramid(fov=0, z=0, channel=0, timepoint=0, level=1)
        assert level1.shape[-2] == raw.shape[-2] // 2
        assert level1.shape[-1] == raw.shape[-1] // 2
        assert (0, 0, 0, 0, 1) in engine._pyramid_cache

    def test_get_pyramid_cache_hit_returns_same_array(
        self, individual_acquisition,
    ) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        first = engine._get_pyramid(fov=0, z=0, channel=0, timepoint=0, level=2)
        second = engine._get_pyramid(fov=0, z=0, channel=0, timepoint=0, level=2)
        assert first is second


class TestViewportEnginePickLevel:
    def test_level_zero_when_zoomed_in(self, individual_acquisition) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        level = engine._pick_level(
            viewport=(0.0, 0.0, 0.1, 0.1),
            screen_width=10000, screen_height=10000,
        )
        assert level == 0

    def test_higher_level_when_zoomed_out(self, individual_acquisition) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        level = engine._pick_level(
            viewport=(0.0, 0.0, 100.0, 100.0),
            screen_width=100, screen_height=100,
        )
        assert level >= 1

    def test_level_capped_at_max(self, individual_acquisition) -> None:
        from squid_tools.viewer.pyramid import MAX_PYRAMID_LEVEL
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        level = engine._pick_level(
            viewport=(0.0, 0.0, 100000.0, 100000.0),
            screen_width=1, screen_height=1,
        )
        assert level == MAX_PYRAMID_LEVEL

    def test_zero_screen_size_returns_level_zero(
        self, individual_acquisition,
    ) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        assert engine._pick_level(
            viewport=(0.0, 0.0, 1.0, 1.0), screen_width=0, screen_height=0,
        ) == 0


class TestViewportEngineCompositeWithPyramid:
    def test_level_override_passes_through(self, individual_acquisition) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        bb = engine.bounding_box()
        tiles_level0 = engine.get_composite_tiles(
            viewport=bb, screen_width=800, screen_height=600,
            active_channels=[0], channel_names=["C1"],
            channel_clims={0: (0.0, 1.0)},
            z=0, timepoint=0,
            level_override=0,
        )
        tiles_level2 = engine.get_composite_tiles(
            viewport=bb, screen_width=800, screen_height=600,
            active_channels=[0], channel_names=["C1"],
            channel_clims={0: (0.0, 1.0)},
            z=0, timepoint=0,
            level_override=2,
        )
        assert len(tiles_level0) == len(tiles_level2)
        assert any(k[4] == 2 for k in engine._pyramid_cache)

    def test_auto_level_selects_when_override_none(
        self, individual_acquisition,
    ) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        bb = engine.bounding_box()
        huge_vp = (bb[0] - 100.0, bb[1] - 100.0, bb[2] + 100.0, bb[3] + 100.0)
        engine.get_composite_tiles(
            viewport=huge_vp, screen_width=50, screen_height=50,
            active_channels=[0], channel_names=["C1"],
            channel_clims={0: (0.0, 1.0)},
            z=0, timepoint=0,
        )
        assert any(k[4] >= 1 for k in engine._pyramid_cache)


class TestViewportEngineGetVolume:
    def test_get_volume_shape_z_y_x(self, individual_acquisition) -> None:
        import numpy as np

        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        vol = engine.get_volume(fov=0, channel=0, timepoint=0)
        assert vol.ndim == 3
        nz = engine._acquisition.z_stack.nz if engine._acquisition.z_stack else 1
        assert vol.shape[0] == nz
        # First plane matches the raw single-plane read
        raw0 = engine._load_raw(fov=0, z=0, channel=0, timepoint=0)
        assert np.array_equal(vol[0], raw0)

    def test_get_volume_with_pyramid_level(self, individual_acquisition) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        vol0 = engine.get_volume(fov=0, channel=0, timepoint=0, level=0)
        vol1 = engine.get_volume(fov=0, channel=0, timepoint=0, level=1)
        assert vol1.shape[0] == vol0.shape[0]
        assert vol1.shape[1] == vol0.shape[1] // 2
        assert vol1.shape[2] == vol0.shape[2] // 2

    def test_get_volume_no_acquisition_raises(self) -> None:
        import pytest

        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        with pytest.raises(RuntimeError, match="No acquisition"):
            engine.get_volume(fov=0, channel=0, timepoint=0)

    # all_volumes_for_region was removed in v1 — it was unbounded
    # (~48 GB on the mouse-brain dataset, no GUI binding). Streaming
    # whole-region volume access is a v2 task; see
    # docs/superpowers/specs/2026-04-26-streaming-region-ops-v2.md.


class TestViewportEngineVoxelSize:
    def test_voxel_size_with_z_stack(self, individual_acquisition) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        vx, vy, vz = engine.voxel_size_um()
        assert vx > 0 and vy > 0 and vz > 0
        assert vx == vy  # square pixels
        # With a multi-plane z-stack, vz is delta_z in microns
        if (
            engine._acquisition.z_stack is not None
            and engine._acquisition.z_stack.nz > 1
        ):
            expected = engine._acquisition.z_stack.delta_z_mm * 1000.0
            assert vz == expected

    def test_voxel_size_no_acquisition(self) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        vx, vy, vz = engine.voxel_size_um()
        assert (vx, vy, vz) == (vx, vy, vz)  # doesn't crash
