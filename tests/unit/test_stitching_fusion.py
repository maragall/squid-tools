"""Tests for tile fusion."""

import numpy as np

from squid_tools.processing.stitching.fusion import accumulate_tile_shard, normalize_shard


class TestFusion:
    def test_accumulate_single_tile(self) -> None:
        fused = np.zeros((1, 64, 64), dtype=np.float32)
        weight = np.zeros((1, 64, 64), dtype=np.float32)
        tile = np.ones((1, 32, 32), dtype=np.float32)
        w2d = np.ones((32, 32), dtype=np.float32)
        accumulate_tile_shard(fused, weight, tile, w2d, 0, 0)
        assert fused[0, 0, 0] == 1.0
        assert weight[0, 0, 0] == 1.0

    def test_accumulate_overlap(self) -> None:
        fused = np.zeros((1, 64, 64), dtype=np.float32)
        weight = np.zeros((1, 64, 64), dtype=np.float32)
        tile1 = np.full((1, 32, 32), 2.0, dtype=np.float32)
        tile2 = np.full((1, 32, 32), 4.0, dtype=np.float32)
        w2d = np.ones((32, 32), dtype=np.float32)
        accumulate_tile_shard(fused, weight, tile1, w2d, 0, 0)
        accumulate_tile_shard(fused, weight, tile2, w2d, 0, 16)  # overlap at cols 16-31
        # Overlap region: accumulated = 2 + 4 = 6, weight = 2
        assert fused[0, 0, 20] == 6.0
        assert weight[0, 0, 20] == 2.0

    def test_normalize(self) -> None:
        fused = np.full((1, 10, 10), 6.0, dtype=np.float32)
        weight = np.full((1, 10, 10), 2.0, dtype=np.float32)
        normalize_shard(fused, weight)
        assert np.isclose(fused[0, 5, 5], 3.0)

    def test_normalize_zero_weight(self) -> None:
        fused = np.full((1, 10, 10), 6.0, dtype=np.float32)
        weight = np.zeros((1, 10, 10), dtype=np.float32)
        normalize_shard(fused, weight)
        assert fused[0, 5, 5] == 0.0  # zero weight -> zero output
