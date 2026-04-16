"""Stitcher plugin wrapper for TileFusion algorithms.

Implements ProcessingPlugin ABC. Uses process_region() for spatial
stitching (multiple tiles + positions -> fused image).
"""

from __future__ import annotations

from typing import Any

import numpy as np
from pydantic import BaseModel

from squid_tools.core.data_model import Acquisition, FOVPosition, OpticalMetadata
from squid_tools.processing.base import ProcessingPlugin
from squid_tools.processing.stitching.fusion import (
    accumulate_tile_shard,
    normalize_shard,
)
from squid_tools.processing.stitching.utils import make_1d_profile


class StitcherParams(BaseModel):
    """Parameters for tile stitching."""

    pixel_size_um: float = 0.325
    blend_pixels: int = 32
    do_register: bool = True
    downsample_factor: int = 4
    ssim_threshold: float = 0.0
    ssim_window: int = 7
    max_shift_pixels: int = 50


class StitcherPlugin(ProcessingPlugin):
    """Tile registration and fusion using absorbed TileFusion algorithms."""

    name = "Stitcher"
    category = "stitching"
    requires_gpu = False

    def parameters(self) -> type[BaseModel]:
        return StitcherParams

    def validate(self, acq: Acquisition) -> list[str]:
        return []

    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        """Single-frame passthrough (stitching is a region operation)."""
        return frames

    def process_region(
        self,
        frames: dict[int, np.ndarray],
        positions: list[FOVPosition],
        params: BaseModel,
    ) -> np.ndarray | None:
        """Stitch tiles: register pairwise, optimize globally, fuse with blending."""
        assert isinstance(params, StitcherParams)

        if len(frames) == 0:
            return None
        if len(frames) == 1:
            return next(iter(frames.values()))

        # Build position array (y, x) in pixels
        pos_map = {p.fov_index: p for p in positions}
        tile_indices = sorted(frames.keys())
        tile_positions_px: list[tuple[float, float]] = []
        for idx in tile_indices:
            p = pos_map[idx]
            y_px = p.y_mm * 1000 / params.pixel_size_um
            x_px = p.x_mm * 1000 / params.pixel_size_um
            tile_positions_px.append((y_px, x_px))

        # Get tile shape (assume all same size)
        sample = frames[tile_indices[0]]
        tile_h, tile_w = sample.shape[:2]

        # Optional: pairwise registration
        if params.do_register and len(tile_indices) > 1:
            tile_positions_px = self._register_tiles(
                frames,
                tile_indices,
                tile_positions_px,
                (tile_h, tile_w),
                params,
            )

        # Fuse
        return self._fuse_tiles(
            frames,
            tile_indices,
            tile_positions_px,
            (tile_h, tile_w),
            params.blend_pixels,
        )

    def _register_tiles(
        self,
        frames: dict[int, np.ndarray],
        tile_indices: list[int],
        positions: list[tuple[float, float]],
        tile_shape: tuple[int, int],
        params: StitcherParams,
    ) -> list[tuple[float, float]]:
        """Pairwise registration + global optimization."""
        from squid_tools.processing.stitching.optimization import (
            links_from_pairwise_metrics,
            two_round_optimization,
        )
        from squid_tools.processing.stitching.registration import (
            find_adjacent_pairs,
            register_pair_worker,
        )

        pixel_size = (1.0, 1.0)  # positions already in pixels
        pairs = find_adjacent_pairs(positions, pixel_size, tile_shape, min_overlap=15)

        if not pairs:
            return positions

        # Register each pair
        df = (params.downsample_factor, params.downsample_factor)
        pairwise_metrics: dict[tuple[int, int], tuple[int, int, float]] = {}

        for i_pos, j_pos, _dy, _dx, _ov_y, _ov_x in pairs:
            tile_i = frames[tile_indices[i_pos]].astype(np.float32)
            tile_j = frames[tile_indices[j_pos]].astype(np.float32)

            result = register_pair_worker((
                i_pos,
                j_pos,
                tile_i,
                tile_j,
                df,
                params.ssim_window,
                params.ssim_threshold,
                (params.max_shift_pixels, params.max_shift_pixels),
            ))
            _, _, dy_s, dx_s, score = result
            if dy_s is not None:
                # Combine nominal offset with registration refinement
                nom_dy = positions[j_pos][0] - positions[i_pos][0]
                nom_dx = positions[j_pos][1] - positions[i_pos][1]
                pairwise_metrics[(i_pos, j_pos)] = (
                    int(nom_dy + dy_s),
                    int(nom_dx + dx_s),
                    score,
                )

        if not pairwise_metrics:
            return positions

        links = links_from_pairwise_metrics(pairwise_metrics)
        shifts = two_round_optimization(
            links,
            n_tiles=len(tile_indices),
            fixed_indices=[0],
            rel_thresh=3.0,
            abs_thresh=50.0,
            iterative=False,
        )

        # Apply shifts to positions
        new_positions = []
        for i, (y, x) in enumerate(positions):
            new_positions.append((y + shifts[i, 0], x + shifts[i, 1]))
        return new_positions

    def _fuse_tiles(
        self,
        frames: dict[int, np.ndarray],
        tile_indices: list[int],
        positions: list[tuple[float, float]],
        tile_shape: tuple[int, int],
        blend_pixels: int,
    ) -> np.ndarray:
        """Fuse tiles using weighted blending."""
        tile_h, tile_w = tile_shape

        # Compute output bounds
        all_y = [p[0] for p in positions]
        all_x = [p[1] for p in positions]
        min_y, min_x = min(all_y), min(all_x)
        max_y = max(all_y) + tile_h
        max_x = max(all_x) + tile_w

        out_h = int(np.ceil(max_y - min_y))
        out_w = int(np.ceil(max_x - min_x))

        fused = np.zeros((1, out_h, out_w), dtype=np.float32)
        weight = np.zeros((1, out_h, out_w), dtype=np.float32)

        # Weight profile
        wy = make_1d_profile(tile_h, blend_pixels)
        wx = make_1d_profile(tile_w, blend_pixels)
        w2d = np.outer(wy, wx)

        for i, idx in enumerate(tile_indices):
            tile = frames[idx].astype(np.float32)
            if tile.ndim == 2:
                tile = tile[np.newaxis]  # (1, H, W)

            y_off = int(np.round(positions[i][0] - min_y))
            x_off = int(np.round(positions[i][1] - min_x))
            accumulate_tile_shard(fused, weight, tile, w2d, y_off, x_off)

        normalize_shard(fused, weight)
        return fused[0]  # return 2D

    def default_params(self, optical: OpticalMetadata | None = None) -> BaseModel:
        px = optical.pixel_size_um if optical and optical.pixel_size_um else 0.325
        return StitcherParams(pixel_size_um=px)

    def test_cases(self) -> list[dict[str, Any]]:
        h, w = 64, 64
        tile1 = np.random.rand(h, w).astype(np.float32)
        tile2 = np.random.rand(h, w).astype(np.float32)
        return [{"frames": {0: tile1, 1: tile2}, "description": "2-tile stitch"}]
