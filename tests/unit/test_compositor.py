"""Tests for the multi-channel compositor."""

from __future__ import annotations

import numpy as np
import pytest

from squid_tools.viewer.compositor import (
    DEFAULT_BACKEND,
    Backend,
    composite_channels,
    composite_volume_channels,
)


class TestBackendEnum:
    def test_enum_values(self) -> None:
        assert Backend.NUMPY.value == "numpy"
        assert Backend.CUPY.value == "cupy"

    def test_default_backend_is_a_backend(self) -> None:
        assert DEFAULT_BACKEND in (Backend.NUMPY, Backend.CUPY)


class TestCompositeValidation:
    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one channel"):
            composite_channels([], [], [])

    def test_length_mismatch_raises(self) -> None:
        frame = np.zeros((4, 4), dtype=np.float32)
        with pytest.raises(ValueError, match="same length"):
            composite_channels(
                [frame, frame], [(0.0, 1.0)], [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            )

    def test_non_2d_frame_raises(self) -> None:
        frame3d = np.zeros((2, 4, 4), dtype=np.float32)
        with pytest.raises(ValueError, match="frames must be 2D"):
            composite_channels([frame3d], [(0.0, 1.0)], [(1.0, 0.0, 0.0)])

    def test_mismatched_frame_shapes_raise(self) -> None:
        a = np.zeros((4, 4), dtype=np.float32)
        b = np.zeros((5, 4), dtype=np.float32)
        with pytest.raises(ValueError, match="same shape"):
            composite_channels(
                [a, b], [(0.0, 1.0), (0.0, 1.0)],
                [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            )


class TestCompositeNumpyBackend:
    def test_single_red_channel_full_bright(self) -> None:
        frame = np.ones((4, 4), dtype=np.float32)
        out = composite_channels(
            [frame], [(0.0, 1.0)], [(1.0, 0.0, 0.0)],
            backend=Backend.NUMPY,
        )
        assert out.shape == (4, 4, 3)
        assert out.dtype == np.float32
        assert np.allclose(out[..., 0], 1.0)
        assert np.allclose(out[..., 1], 0.0)
        assert np.allclose(out[..., 2], 0.0)

    def test_single_red_channel_half_bright(self) -> None:
        frame = np.full((4, 4), 0.5, dtype=np.float32)
        out = composite_channels(
            [frame], [(0.0, 1.0)], [(1.0, 0.0, 0.0)],
            backend=Backend.NUMPY,
        )
        assert np.allclose(out[..., 0], 0.5)
        assert np.allclose(out[..., 1:], 0.0)

    def test_two_channels_red_and_green(self) -> None:
        red_frame = np.ones((4, 4), dtype=np.float32)
        green_frame = np.ones((4, 4), dtype=np.float32)
        out = composite_channels(
            [red_frame, green_frame],
            [(0.0, 1.0), (0.0, 1.0)],
            [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            backend=Backend.NUMPY,
        )
        assert np.allclose(out[..., 0], 1.0)
        assert np.allclose(out[..., 1], 1.0)
        assert np.allclose(out[..., 2], 0.0)

    def test_clim_normalization(self) -> None:
        frame = np.full((4, 4), 1000.0, dtype=np.float32)
        out = composite_channels(
            [frame], [(500.0, 1500.0)], [(1.0, 0.0, 0.0)],
            backend=Backend.NUMPY,
        )
        assert np.allclose(out[..., 0], 0.5)

    def test_value_below_clim_clips_to_zero(self) -> None:
        frame = np.zeros((2, 2), dtype=np.float32)
        out = composite_channels(
            [frame], [(10.0, 20.0)], [(1.0, 0.0, 0.0)],
            backend=Backend.NUMPY,
        )
        assert np.allclose(out, 0.0)

    def test_value_above_clim_clips_to_color(self) -> None:
        frame = np.full((2, 2), 1000.0, dtype=np.float32)
        out = composite_channels(
            [frame], [(10.0, 20.0)], [(1.0, 0.0, 0.0)],
            backend=Backend.NUMPY,
        )
        assert np.allclose(out[..., 0], 1.0)
        assert np.allclose(out[..., 1:], 0.0)

    def test_zero_width_clim_does_not_divide_by_zero(self) -> None:
        frame = np.full((2, 2), 5.0, dtype=np.float32)
        out = composite_channels(
            [frame], [(5.0, 5.0)], [(1.0, 0.0, 0.0)],
            backend=Backend.NUMPY,
        )
        assert out.shape == (2, 2, 3)
        assert np.all(np.isfinite(out))

    def test_output_float32(self) -> None:
        frame = np.ones((2, 2), dtype=np.uint16) * 100
        out = composite_channels(
            [frame], [(0.0, 200.0)], [(1.0, 0.0, 0.0)],
            backend=Backend.NUMPY,
        )
        assert out.dtype == np.float32


class TestBackendOverride:
    def test_explicit_numpy_backend(self) -> None:
        frame = np.ones((4, 4), dtype=np.float32)
        out = composite_channels(
            [frame], [(0.0, 1.0)], [(1.0, 0.0, 0.0)],
            backend=Backend.NUMPY,
        )
        assert out.shape == (4, 4, 3)


class TestBackendLogging:
    def test_default_backend_logged_at_import(self, caplog) -> None:
        import importlib
        import logging

        import squid_tools.viewer.compositor as compositor_mod

        caplog.set_level(logging.INFO, logger="squid_tools.viewer.compositor")
        importlib.reload(compositor_mod)
        messages = [
            r.getMessage() for r in caplog.records
            if r.name == "squid_tools.viewer.compositor"
            and r.levelno == logging.INFO
        ]
        assert any("compositor backend:" in m for m in messages)


class TestCompositorIntegrationWithEngine:
    def test_composite_tiles_uses_new_compositor(
        self, individual_acquisition,
    ) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        bb = engine.bounding_box()

        # Lookup channel names from acquisition
        acq = engine._acquisition if hasattr(engine, "_acquisition") else None
        channel_names = (
            [ch.name for ch in acq.channels]
            if acq is not None
            else ["channel_0", "channel_1"]
        )

        tiles = engine.get_composite_tiles(
            viewport=bb, screen_width=100, screen_height=100,
            active_channels=list(range(len(channel_names))),
            channel_names=channel_names,
            channel_clims={
                i: (0.0, 1.0) for i in range(len(channel_names))
            },
            z=0, timepoint=0,
            level_override=0,
        )
        assert len(tiles) > 0
        first = tiles[0]
        data = first.data if hasattr(first, "data") else first[0]
        assert data.ndim == 3
        assert data.shape[-1] == 3
        assert data.dtype == np.float32


class TestCompositeVolumeChannels:
    def test_single_channel_rgb_plus_alpha(self) -> None:
        vol = np.ones((4, 8, 8), dtype=np.float32)
        out = composite_volume_channels(
            [vol], [(0.0, 1.0)], [(1.0, 0.0, 0.0)],
        )
        assert out.shape == (4, 8, 8, 4)
        assert out.dtype == np.float32
        assert np.allclose(out[..., 0], 1.0)
        assert np.allclose(out[..., 1:3], 0.0)
        # Alpha equals normalized value
        assert np.allclose(out[..., 3], 1.0)

    def test_two_channels_alpha_is_max(self) -> None:
        red_vol = np.ones((2, 4, 4), dtype=np.float32)
        green_vol = np.full((2, 4, 4), 0.5, dtype=np.float32)
        out = composite_volume_channels(
            [red_vol, green_vol],
            [(0.0, 1.0), (0.0, 1.0)],
            [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        )
        # Alpha is max across channels — red is brighter (1.0) vs green (0.5)
        assert np.allclose(out[..., 3], 1.0)

    def test_zero_signal_has_zero_alpha(self) -> None:
        vol = np.zeros((2, 4, 4), dtype=np.float32)
        out = composite_volume_channels(
            [vol], [(0.0, 1.0)], [(1.0, 1.0, 1.0)],
        )
        assert np.allclose(out[..., 3], 0.0)
        assert np.allclose(out[..., :3], 0.0)

    def test_clim_normalization_3d(self) -> None:
        vol = np.full((2, 4, 4), 1000.0, dtype=np.float32)
        out = composite_volume_channels(
            [vol], [(500.0, 1500.0)], [(1.0, 0.0, 0.0)],
        )
        assert np.allclose(out[..., 0], 0.5)
        assert np.allclose(out[..., 3], 0.5)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one channel"):
            composite_volume_channels([], [], [])

    def test_length_mismatch_raises(self) -> None:
        vol = np.zeros((2, 4, 4), dtype=np.float32)
        with pytest.raises(ValueError, match="same length"):
            composite_volume_channels(
                [vol, vol], [(0.0, 1.0)],
                [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            )

    def test_non_3d_raises(self) -> None:
        vol2d = np.zeros((4, 4), dtype=np.float32)
        with pytest.raises(ValueError, match="must be 3D"):
            composite_volume_channels(
                [vol2d], [(0.0, 1.0)], [(1.0, 0.0, 0.0)],
            )

    def test_mismatched_shape_raises(self) -> None:
        a = np.zeros((2, 4, 4), dtype=np.float32)
        b = np.zeros((2, 5, 4), dtype=np.float32)
        with pytest.raises(ValueError, match="same shape"):
            composite_volume_channels(
                [a, b],
                [(0.0, 1.0), (0.0, 1.0)],
                [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            )
