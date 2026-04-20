"""Tests for the multi-channel compositor."""

from __future__ import annotations

import numpy as np
import pytest

from squid_tools.viewer.compositor import (
    DEFAULT_BACKEND,
    Backend,
    composite_channels,
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
