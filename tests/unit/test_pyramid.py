"""Tests for pyramid decimation."""

from __future__ import annotations

import numpy as np
import pytest

from squid_tools.viewer.pyramid import MAX_PYRAMID_LEVEL, downsample_frame


class TestMaxLevel:
    def test_constant_value(self) -> None:
        assert MAX_PYRAMID_LEVEL == 5


class TestDownsampleFrame:
    def test_level_zero_returns_original(self) -> None:
        frame = np.arange(64, dtype=np.float32).reshape(8, 8)
        out = downsample_frame(frame, 0)
        assert out is frame

    def test_level_one_halves_both_dims_2d(self) -> None:
        frame = np.arange(64, dtype=np.float32).reshape(8, 8)
        out = downsample_frame(frame, 1)
        assert out.shape == (4, 4)
        assert out[0, 0] == frame[0, 0]
        assert out[1, 1] == frame[2, 2]

    def test_level_two_quarters_both_dims_2d(self) -> None:
        frame = np.arange(64, dtype=np.float32).reshape(8, 8)
        out = downsample_frame(frame, 2)
        assert out.shape == (2, 2)
        assert out[0, 0] == frame[0, 0]
        assert out[1, 1] == frame[4, 4]

    def test_3d_frame_preserves_leading_axis(self) -> None:
        frame = np.arange(3 * 8 * 8, dtype=np.float32).reshape(3, 8, 8)
        out = downsample_frame(frame, 1)
        assert out.shape == (3, 4, 4)
        assert out[0, 0, 0] == frame[0, 0, 0]
        assert out[1, 1, 1] == frame[1, 2, 2]

    def test_returns_copy_at_level_one(self) -> None:
        frame = np.arange(16, dtype=np.float32).reshape(4, 4)
        out = downsample_frame(frame, 1)
        out[0, 0] = 999
        assert frame[0, 0] == 0

    def test_negative_level_raises(self) -> None:
        frame = np.zeros((4, 4), dtype=np.float32)
        with pytest.raises(ValueError, match="level must be >= 0"):
            downsample_frame(frame, -1)

    def test_1d_frame_raises(self) -> None:
        frame = np.zeros(4, dtype=np.float32)
        with pytest.raises(ValueError, match="must be 2D or 3D"):
            downsample_frame(frame, 1)

    def test_4d_frame_raises(self) -> None:
        frame = np.zeros((2, 2, 2, 2), dtype=np.float32)
        with pytest.raises(ValueError, match="must be 2D or 3D"):
            downsample_frame(frame, 1)
