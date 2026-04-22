"""Stitcher plugin wrapper for TileFusion algorithms.

Implements ProcessingPlugin ABC. Uses process_region() for spatial
stitching (multiple tiles + positions -> fused image).
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


class StitcherParams(BaseModel):
    """Parameters for tile stitching.

    Defaults ported from Cephla-Lab/stitcher tilefusion.core.TileFusion
    (__init__ defaults). pixel_size_um is REQUIRED (no hardcoded fallback) —
    default_params() derives it from the objective metadata.
    """

    pixel_size_um: float                      # from acquisition metadata
    blend_pixels: int = 0                     # TileFusion default (no blend)
    do_register: bool = True
    downsample_factor: int = 1                # TileFusion downsample_factors=(1,1)
    ssim_threshold: float = 0.5               # TileFusion threshold=0.5
    ssim_window: int = 15                     # TileFusion ssim_window=15
    max_shift_pixels: int = 100               # TileFusion max_shift=(100,100)


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

    def run_live(self, selection, engine, params, progress):
        """Progressive pairwise registration with live position updates."""
        from squid_tools.processing.stitching.optimization import (
            links_from_pairwise_metrics,
            two_round_optimization,
        )
        from squid_tools.processing.stitching.registration import (
            compute_pair_bounds,
            find_adjacent_pairs,
            register_pair_worker,
        )

        # Phase 1: Find pairs
        progress("Finding pairs", 0, 1)
        indices = selection if selection else engine.all_fov_indices()
        if len(indices) < 2:
            progress("Finding pairs", 1, 1)
            return

        nominal = engine.get_nominal_positions(indices)
        pixel_size = engine.pixel_size_um
        sorted_ids = sorted(nominal.keys())
        positions_px = [
            (nominal[i][1] * 1000.0 / pixel_size, nominal[i][0] * 1000.0 / pixel_size)
            for i in sorted_ids
        ]
        # Pick any loaded frame to determine tile shape
        sample_frame = engine.get_raw_frame(sorted_ids[0], z=0, channel=0, timepoint=0)
        tile_shape = sample_frame.shape[:2]
        pairs = find_adjacent_pairs(
            positions_px, (1.0, 1.0), tile_shape, min_overlap=15,
        )
        progress("Finding pairs", 1, 1)
        if not pairs:
            return

        # Compute per-pair overlap bounds so we register on just the overlap
        # strip, not the whole tile. This mirrors the reference stitcher
        # (_audit/stitcher/src/tilefusion/core.py:595-603, 660-672):
        # phase cross-correlation needs the shared region, not the full frame.
        pair_bounds = compute_pair_bounds(pairs, tile_shape)

        # Phase 2: Register progressively
        total = len(pair_bounds)
        logger.info("Stitcher: pairwise registration on %d tiles", len(sorted_ids))
        pairwise_metrics: dict[tuple[int, int], tuple[int, int, float]] = {}

        for k, bounds in enumerate(pair_bounds):
            progress("Registering", k, total)
            (
                i_pos, j_pos,
                (by_i_0, by_i_1), (bx_i_0, bx_i_1),
                (by_j_0, by_j_1), (bx_j_0, bx_j_1),
            ) = bounds
            frame_i = engine.get_raw_frame(
                sorted_ids[i_pos], z=0, channel=0, timepoint=0,
            ).astype("float32")
            frame_j = engine.get_raw_frame(
                sorted_ids[j_pos], z=0, channel=0, timepoint=0,
            ).astype("float32")
            patch_i = frame_i[by_i_0:by_i_1, bx_i_0:bx_i_1]
            patch_j = frame_j[by_j_0:by_j_1, bx_j_0:bx_j_1]
            df = (params.downsample_factor, params.downsample_factor)
            result = register_pair_worker((
                i_pos, j_pos, patch_i, patch_j, df,
                params.ssim_window, params.ssim_threshold,
                (params.max_shift_pixels, params.max_shift_pixels),
            ))
            _, _, dy_s, dx_s, score = result
            if dy_s is not None:
                nom_dy = positions_px[j_pos][0] - positions_px[i_pos][0]
                nom_dx = positions_px[j_pos][1] - positions_px[i_pos][1]
                pairwise_metrics[(i_pos, j_pos)] = (
                    int(nom_dy + dy_s), int(nom_dx + dx_s), score,
                )
        progress("Registering", total, total)

        if not pairwise_metrics:
            return

        # Phase 3: Optimize & publish positions
        logger.info("Stitcher: global optimization (%d positions)", len(sorted_ids))
        progress("Optimizing", 0, 1)
        links = links_from_pairwise_metrics(pairwise_metrics)
        try:
            shifts = two_round_optimization(
                links,
                n_tiles=len(sorted_ids),
                fixed_indices=[0],
                rel_thresh=3.0, abs_thresh=50.0, iterative=False,
            )
        except np.linalg.LinAlgError:
            progress("Optimizing", 1, 1)
            return
        overrides: dict[int, tuple[float, float]] = {}
        for i, idx in enumerate(sorted_ids):
            ox, oy = nominal[idx]
            overrides[idx] = (
                ox + float(shifts[i, 1]) * pixel_size / 1000.0,
                oy + float(shifts[i, 0]) * pixel_size / 1000.0,
            )
        engine.set_position_overrides(overrides)
        progress("Optimizing", 1, 1)

    def fuse_region_to_array(
        self,
        engine,  # ViewportEngine  # noqa: ANN001
        params: StitcherParams,
        *,
        channel: int = 0,
        z: int = 0,
        timepoint: int = 0,
        fov_indices: set[int] | None = None,
    ) -> np.ndarray:
        """Fuse the given tiles into a single 2D image using position overrides.

        Ports the fusion phase from Cephla-Lab/stitcher's TileFusion — the
        missing step after run_live's registration + optimization. Returns a
        2D float32 array sized to the stitched bounding box.

        Raises RuntimeError if the engine has no active acquisition.
        """
        if not engine.is_loaded():
            raise RuntimeError("Engine has no acquisition loaded")
        indices = fov_indices if fov_indices is not None else engine.all_fov_indices()
        if not indices:
            raise ValueError("No FOVs to fuse")
        sorted_ids = sorted(indices)

        frames: dict[int, np.ndarray] = {}
        positions: list[FOVPosition] = []
        for idx in sorted_ids:
            frames[idx] = engine.get_raw_frame(
                idx, z=z, channel=channel, timepoint=timepoint,
            )
            # Honor engine's position overrides (so fusion uses REGISTERED coords)
            pos = engine._position_overrides.get(idx)
            if pos is None:
                # Nominal from the spatial index
                fov = next(
                    f for f in engine._index._fovs if f.fov_index == idx
                )
                pos = (fov.x_mm, fov.y_mm)
            positions.append(FOVPosition(
                fov_index=idx, x_mm=pos[0], y_mm=pos[1],
            ))

        fused = self.process_region(frames, positions, params)
        if fused is None:
            raise RuntimeError("process_region returned None")
        return fused

    def default_params(self, optical: OpticalMetadata | None = None) -> BaseModel:
        """Derive params from acquisition metadata. pixel_size_um is REQUIRED.

        Raises ValueError if no acquisition-derived pixel size is available —
        refuses to fall back to a hardcoded fiction.
        """
        if optical is None or not optical.pixel_size_um:
            raise ValueError(
                "StitcherPlugin.default_params needs OpticalMetadata.pixel_size_um "
                "from the acquisition. Hardcoded fallbacks are off the table — "
                "check that the acquisition reader populated .optical correctly."
            )
        return StitcherParams(pixel_size_um=optical.pixel_size_um)

    def test_cases(self) -> list[dict[str, Any]]:
        h, w = 64, 64
        tile1 = np.random.rand(h, w).astype(np.float32)
        tile2 = np.random.rand(h, w).astype(np.float32)
        return [{"frames": {0: tile1, 1: tile2}, "description": "2-tile stitch"}]
