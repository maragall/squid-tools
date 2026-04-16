"""Tests for stitching GPU/CPU utilities."""

import numpy as np

from squid_tools.processing.stitching.utils import (
    USING_GPU,
    compute_ssim,
    make_1d_profile,
    shift_array,
    to_numpy,
    xp,
)


class TestUtils:
    def test_using_gpu_is_bool(self) -> None:
        assert isinstance(USING_GPU, bool)

    def test_xp_is_numpy_or_cupy(self) -> None:
        assert hasattr(xp, "array")
        assert hasattr(xp, "zeros")

    def test_to_numpy(self) -> None:
        arr = xp.ones((5, 5), dtype=xp.float32)
        result = to_numpy(arr)
        assert isinstance(result, np.ndarray)

    def test_shift_array(self) -> None:
        arr = np.zeros((10, 10), dtype=np.float32)
        arr[5, 5] = 1.0
        shifted = shift_array(arr, shift_vec=(1.0, 0.0))
        assert isinstance(shifted, np.ndarray)
        assert shifted.shape == (10, 10)

    def test_compute_ssim(self) -> None:
        arr = np.random.rand(64, 64).astype(np.float32)
        score = compute_ssim(arr, arr, win_size=7)
        assert 0.99 <= score <= 1.01  # identical images -> SSIM ~1.0

    def test_make_1d_profile(self) -> None:
        prof = make_1d_profile(100, blend=20)
        assert prof.shape == (100,)
        assert prof[0] < prof[50]  # ramp at edges
        assert np.isclose(prof[50], 1.0)

    def test_make_1d_profile_short(self) -> None:
        prof = make_1d_profile(10, blend=20)  # blend > length/2
        assert prof.shape == (10,)
