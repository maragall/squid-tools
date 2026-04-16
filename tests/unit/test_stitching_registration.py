"""Tests for tile registration."""

import numpy as np

from squid_tools.processing.stitching.registration import (
    find_adjacent_pairs,
    register_and_score,
)


class TestRegistration:
    def test_register_identical_patches(self) -> None:
        patch = np.random.rand(64, 64).astype(np.float32)
        shift, score = register_and_score(patch, patch, win_size=7)
        assert shift is not None
        assert abs(shift[0]) < 2  # near-zero shift
        assert abs(shift[1]) < 2
        assert score > 0.9  # high SSIM

    def test_register_shifted_patches(self) -> None:
        base = np.random.rand(64, 64).astype(np.float32)
        from scipy.ndimage import shift as ndi_shift

        shifted = ndi_shift(base, (3.0, 5.0), order=1)
        result_shift, score = register_and_score(base, shifted, win_size=7)
        assert result_shift is not None
        # Should recover approximate shift
        assert abs(result_shift[0] - (-3.0)) < 3
        assert abs(result_shift[1] - (-5.0)) < 3

    def test_find_adjacent_pairs_grid(self) -> None:
        # 2x2 grid with known positions
        positions = [(0, 0), (0, 100), (100, 0), (100, 100)]
        pixel_size = (1.0, 1.0)
        tile_shape = (128, 128)
        pairs = find_adjacent_pairs(positions, pixel_size, tile_shape, min_overlap=15)
        assert len(pairs) > 0
        # Should find horizontal and vertical neighbors
        pair_indices = [(p[0], p[1]) for p in pairs]
        assert (0, 1) in pair_indices or (1, 0) in pair_indices  # horizontal

    def test_find_no_pairs_far_apart(self) -> None:
        positions = [(0, 0), (0, 1000)]  # too far apart
        pixel_size = (1.0, 1.0)
        tile_shape = (128, 128)
        pairs = find_adjacent_pairs(positions, pixel_size, tile_shape, min_overlap=15)
        assert len(pairs) == 0
