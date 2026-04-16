"""Tests for data-intensive viewport data manager."""

from pathlib import Path

import numpy as np

from squid_tools.viewer.data_manager import ViewportDataManager
from tests.fixtures.generate_fixtures import create_individual_acquisition


class TestDataManagerBasic:
    def test_instantiate(self) -> None:
        mgr = ViewportDataManager()
        assert mgr is not None

    def test_load_acquisition(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        mgr = ViewportDataManager()
        mgr.load(acq_path)
        assert mgr.acquisition is not None

    def test_get_frame_cached(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        mgr = ViewportDataManager()
        mgr.load(acq_path)
        f1 = mgr.get_frame(region="0", fov=0)
        f2 = mgr.get_frame(region="0", fov=0)
        assert f1 is f2

    def test_get_frame_shape(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        mgr = ViewportDataManager()
        mgr.load(acq_path)
        frame = mgr.get_frame(region="0", fov=0, z=0, channel=0, timepoint=0)
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (128, 128)

    def test_get_region_frames(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        mgr = ViewportDataManager()
        mgr.load(acq_path)
        frames = mgr.get_region_frames(region="0", z=0, channel=0, timepoint=0)
        assert len(frames) == 4

    def test_pixel_size(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        mgr = ViewportDataManager()
        mgr.load(acq_path)
        assert mgr.pixel_size_um == 0.325

    def test_region_ids(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        mgr = ViewportDataManager()
        mgr.load(acq_path)
        assert "0" in mgr.region_ids()


class TestThumbnails:
    def test_generate_thumbnail(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        mgr = ViewportDataManager()
        mgr.load(acq_path)
        thumb = mgr.get_thumbnail(region="0", fov=0, channel=0)
        assert thumb is not None
        assert thumb.shape[0] <= 256 and thumb.shape[1] <= 256

    def test_get_all_thumbnails(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        mgr = ViewportDataManager()
        mgr.load(acq_path)
        thumbs = mgr.get_region_thumbnails(region="0", channel=0)
        assert len(thumbs) == 4  # 2x2 grid


class TestContrastStats:
    def test_compute_contrast_stats(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        mgr = ViewportDataManager()
        mgr.load(acq_path)
        p1, p99 = mgr.get_contrast_stats(region="0", channel=0)
        assert p1 < p99
        assert isinstance(p1, float)
        assert isinstance(p99, float)


class TestPipeline:
    def test_no_pipeline_returns_raw(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        mgr = ViewportDataManager()
        mgr.load(acq_path)
        raw = mgr.get_frame(region="0", fov=0)
        assert raw is not None

    def test_pipeline_transforms_frame(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        mgr = ViewportDataManager()
        mgr.load(acq_path)

        # Add a simple transform
        mgr.set_pipeline([lambda frame: frame.astype(np.float32) * 2.0])

        raw = mgr.get_raw_frame(region="0", fov=0)
        processed = mgr.get_frame(region="0", fov=0)
        assert not np.array_equal(raw, processed)

    def test_toggle_pipeline_off(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        mgr = ViewportDataManager()
        mgr.load(acq_path)
        mgr.set_pipeline([lambda frame: frame.astype(np.float32) * 2.0])
        mgr.set_pipeline([])  # toggle off
        raw = mgr.get_raw_frame(region="0", fov=0)
        processed = mgr.get_frame(region="0", fov=0)
        assert np.array_equal(raw, processed)


class TestViewportLoading:
    def test_get_visible_fovs(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=3, ny=3, nz=1, nc=1, nt=1
        )
        mgr = ViewportDataManager()
        mgr.load(acq_path)
        # Viewport covering only top-left portion (in mm)
        # Fixture grid step is ~0.035mm, tile size ~0.042mm
        # A small viewport should intersect fewer than all 9 tiles
        visible = mgr.get_visible_fov_indices(
            region="0",
            viewport=(0, 0, 0.05, 0.05),  # x_min, y_min, x_max, y_max in mm
        )
        # Should return fewer than all 9 FOVs
        assert len(visible) < 9
        assert len(visible) > 0
