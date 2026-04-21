"""Viewport-aware tile loading engine.

Given viewport bounds + screen size:
1. Query spatial index for visible tiles
2. Compute target resolution (downsample to screen pixels)
3. Load tile from reader (or cache)
4. Downsample to target resolution
5. Return positioned tile data ready for rendering

No pyramids. No pre-computation. Faster than the user's eyes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import zoom as ndi_zoom

from squid_tools.core.cache import MemoryBoundedLRUCache
from squid_tools.core.data_model import Acquisition, FrameKey
from squid_tools.core.readers import detect_reader
from squid_tools.core.readers.base import FormatReader
from squid_tools.viewer.spatial_index import SpatialIndex

logger = logging.getLogger(__name__)


@dataclass
class VisibleTile:
    """A tile ready for rendering."""

    fov_index: int
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    data: np.ndarray  # downsampled to screen resolution


class ViewportEngine:
    """Loads visible tiles on demand, downsampled to screen resolution."""

    def __init__(self, cache_bytes: int = 256 * 1024 * 1024) -> None:
        self._acquisition: Acquisition | None = None
        self._reader: FormatReader | None = None
        self._index: SpatialIndex | None = None
        self._tile_w_mm: float = 0.0
        self._tile_h_mm: float = 0.0
        self._tile_w_px: int = 0
        self._tile_h_px: int = 0
        self._region: str = ""
        self._raw_cache = MemoryBoundedLRUCache(max_bytes=cache_bytes)
        self._display_cache: dict[str, np.ndarray] = {}
        self._pyramid_cache: dict[
            tuple[int, int, int, int, int], np.ndarray,
        ] = {}
        self._last_screen_key: str = ""
        self._pipeline: list = []
        self._contrast: tuple[float, float] | None = None
        self._position_overrides: dict[int, tuple[float, float]] = {}

    def load(self, path: Path, region: str) -> None:
        """Load acquisition and build spatial index for a region."""
        self._reader = detect_reader(path)
        self._acquisition = self._reader.read_metadata(path)
        self._region = region

        # Get tile dimensions from first FOV
        region_obj = self._acquisition.regions[region]
        first_fov = region_obj.fovs[0]
        key = FrameKey(region=region, fov=first_fov.fov_index, z=0, channel=0, timepoint=0)
        first_frame = self._reader.read_frame(key)
        self._tile_h_px, self._tile_w_px = first_frame.shape[:2]
        self._raw_cache.put(f"raw_{region}_{first_fov.fov_index}_0_0_0", first_frame)

        pixel_size = self._acquisition.objective.pixel_size_um
        self._tile_w_mm = self._tile_w_px * pixel_size / 1000
        self._tile_h_mm = self._tile_h_px * pixel_size / 1000

        self._index = SpatialIndex(region_obj, self._tile_w_mm, self._tile_h_mm)

        # Clear caches for new acquisition
        self._display_cache.clear()
        self._pyramid_cache.clear()

        try:
            bb = self.bounding_box()
        except Exception:
            bb = None
        logger.debug(
            "Loaded region=%s bounds=%s fovs=%d",
            region, bb, len(region_obj.fovs),
        )

    def is_loaded(self) -> bool:
        return self._index is not None

    def bounding_box(self) -> tuple[float, float, float, float]:
        """Stage bounding box in mm."""
        if self._index is None:
            return (0, 0, 0, 0)
        return self._index.bounding_box()

    @property
    def tile_size_mm(self) -> tuple[float, float]:
        return (self._tile_w_mm, self._tile_h_mm)

    @property
    def pixel_size_um(self) -> float:
        if self._acquisition is None:
            return 1.0
        return self._acquisition.objective.pixel_size_um

    def set_pipeline(self, transforms: list) -> None:
        """Set processing pipeline (toggle-based)."""
        self._pipeline = transforms
        self._display_cache.clear()

    def set_contrast(self, p1: float, p99: float) -> None:
        """Set global contrast range."""
        self._contrast = (p1, p99)

    def set_position_overrides(self, overrides: dict[int, tuple[float, float]]) -> None:
        """Override tile positions (for registration results).

        overrides: {fov_index: (new_x_mm, new_y_mm)}
        """
        self._position_overrides = overrides
        self._display_cache.clear()

    def clear_position_overrides(self) -> None:
        """Revert to nominal positions."""
        self._position_overrides = {}
        self._display_cache.clear()

    def register_visible_tiles(
        self,
        viewport: tuple[float, float, float, float],
        channel: int = 0,
        z: int = 0,
        timepoint: int = 0,
    ) -> dict[int, tuple[float, float]]:
        """Run pairwise registration on visible tiles.

        Returns dict mapping fov_index -> (registered_x_mm, registered_y_mm).
        Positions are the CORRECTED positions after phase cross-correlation.
        """
        if self._index is None or self._reader is None or self._acquisition is None:
            return {}

        from squid_tools.processing.stitching.optimization import (
            links_from_pairwise_metrics,
            two_round_optimization,
        )
        from squid_tools.processing.stitching.registration import (
            find_adjacent_pairs,
            register_pair_worker,
        )

        x_min, y_min, x_max, y_max = viewport
        visible_fovs = self._index.query(x_min, y_min, x_max, y_max)
        if len(visible_fovs) < 2:
            return {}

        pixel_size = self.pixel_size_um

        # Build position list in pixels for registration
        fov_map = {f.fov_index: f for f in visible_fovs}
        tile_indices = sorted(fov_map.keys())
        positions_px = []
        for idx in tile_indices:
            fov = fov_map[idx]
            y_px = fov.y_mm * 1000 / pixel_size
            x_px = fov.x_mm * 1000 / pixel_size
            positions_px.append((y_px, x_px))

        tile_shape = (self._tile_h_px, self._tile_w_px)
        pixel_size_tuple = (1.0, 1.0)  # positions already in pixels

        # Find adjacent pairs
        pairs = find_adjacent_pairs(positions_px, pixel_size_tuple, tile_shape, min_overlap=15)
        if not pairs:
            return {}

        # Register each pair
        df = (4, 4)  # downsample factor
        pairwise_metrics: dict[tuple[int, int], tuple[int, int, float]] = {}
        for i_pos, j_pos, _dy, _dx, _ov_y, _ov_x in pairs:
            fov_i_idx = tile_indices[i_pos]
            fov_j_idx = tile_indices[j_pos]
            frame_i = self._load_raw(fov_i_idx, z, channel, timepoint).astype(np.float32)
            frame_j = self._load_raw(fov_j_idx, z, channel, timepoint).astype(np.float32)

            result = register_pair_worker((
                i_pos, j_pos, frame_i, frame_j, df, 7, 0.0, (50, 50),
            ))
            _, _, dy_s, dx_s, score = result
            if dy_s is not None:
                nom_dy = positions_px[j_pos][0] - positions_px[i_pos][0]
                nom_dx = positions_px[j_pos][1] - positions_px[i_pos][1]
                pairwise_metrics[(i_pos, j_pos)] = (
                    int(nom_dy + dy_s), int(nom_dx + dx_s), score,
                )

        if not pairwise_metrics:
            return {}

        # Global optimization
        links = links_from_pairwise_metrics(pairwise_metrics)
        try:
            shifts = two_round_optimization(
                links, n_tiles=len(tile_indices), fixed_indices=[0],
                rel_thresh=3.0, abs_thresh=50.0, iterative=False,
            )
        except np.linalg.LinAlgError:
            return {}

        # Convert pixel shifts back to mm
        registered: dict[int, tuple[float, float]] = {}
        for i, idx in enumerate(tile_indices):
            orig = fov_map[idx]
            shift_y_mm = shifts[i, 0] * pixel_size / 1000
            shift_x_mm = shifts[i, 1] * pixel_size / 1000
            registered[idx] = (orig.x_mm + shift_x_mm, orig.y_mm + shift_y_mm)

        return registered

    def compute_contrast(
        self,
        channel: int = 0,
        z: int = 0,
        timepoint: int = 0,
        fov_indices: list[int] | None = None,
        max_samples: int = 10,
    ) -> tuple[float, float]:
        """Sample tiles to compute p1/p99 contrast.

        When fov_indices is provided, sample only from those FOVs (viewport-only).
        Falls back to sampling the first max_samples FOVs when fov_indices is None.
        """
        if self._acquisition is None or self._reader is None:
            return (0.0, 65535.0)

        fovs = self._acquisition.regions[self._region].fovs

        if fov_indices is not None:
            fov_index_set = set(fov_indices)
            sample_fovs = [f for f in fovs if f.fov_index in fov_index_set]
        else:
            sample_fovs = fovs[:max_samples]

        # Limit to max_samples
        sample_fovs = sample_fovs[:max_samples]

        pixels: list[np.ndarray] = []
        rng = np.random.default_rng(42)
        for fov in sample_fovs:
            frame = self._load_raw(fov.fov_index, z, channel, timepoint)
            flat = frame.ravel()
            idx = rng.choice(len(flat), min(1000, len(flat)), replace=False)
            pixels.append(flat[idx])

        if not pixels:
            return (0.0, 65535.0)

        all_px = np.concatenate(pixels)
        p1 = float(np.percentile(all_px, 1))
        p99 = float(np.percentile(all_px, 99))
        if p1 == p99:
            p99 = p1 + 1
        self._contrast = (p1, p99)
        return (p1, p99)

    def get_tiles(
        self,
        viewport: tuple[float, float, float, float],
        screen_width: int,
        screen_height: int,
        channel: int = 0,
        z: int = 0,
        timepoint: int = 0,
    ) -> list[VisibleTile]:
        """Get tiles visible in viewport, downsampled to screen resolution."""
        if self._index is None or self._reader is None:
            return []

        x_min, y_min, x_max, y_max = viewport
        visible_fovs = self._index.query(x_min, y_min, x_max, y_max)

        # How many screen pixels per tile?
        vp_width_mm = max(x_max - x_min, 1e-6)
        mm_per_screen_px = vp_width_mm / max(screen_width, 1)
        target_tile_px = max(4, int(self._tile_w_mm / mm_per_screen_px))
        # Clamp to full resolution
        target_tile_px = min(target_tile_px, self._tile_w_px)

        screen_key = f"{target_tile_px}_{channel}_{z}_{timepoint}"
        cache_invalidated = screen_key != self._last_screen_key
        self._last_screen_key = screen_key

        tiles: list[VisibleTile] = []
        for fov in visible_fovs:
            display_key = f"disp_{fov.fov_index}_{screen_key}"

            if not cache_invalidated and display_key in self._display_cache:
                data = self._display_cache[display_key]
            else:
                raw = self._load_raw(fov.fov_index, z, channel, timepoint)
                # Apply pipeline
                processed = raw.astype(np.float32)
                for transform in self._pipeline:
                    processed = transform(processed)
                # Downsample to screen resolution
                if target_tile_px < self._tile_w_px:
                    factor = target_tile_px / self._tile_w_px
                    data = ndi_zoom(processed, factor, order=0)
                else:
                    data = processed
                self._display_cache[display_key] = data

            pos = self._position_overrides.get(fov.fov_index, (fov.x_mm, fov.y_mm))
            tiles.append(VisibleTile(
                fov_index=fov.fov_index,
                x_mm=pos[0], y_mm=pos[1],
                width_mm=self._tile_w_mm, height_mm=self._tile_h_mm,
                data=data,
            ))

        return tiles

    def get_composite_tiles(
        self,
        viewport: tuple[float, float, float, float],
        screen_width: int,
        screen_height: int,
        active_channels: list[int],
        channel_names: list[str],
        channel_clims: dict[int, tuple[float, float]],
        z: int = 0,
        timepoint: int = 0,
        *,
        level_override: int | None = None,
    ) -> list[VisibleTile]:
        """Get tiles with multi-channel additive composite.

        Each tile's data is an RGB float32 array (H, W, 3) composited
        from all active channels using Cephla colormaps.

        level_override: if given, use this pyramid level; otherwise auto-select
        from viewport/screen geometry via _pick_level.
        """
        from squid_tools.viewer.colormaps import get_channel_rgb
        from squid_tools.viewer.compositor import composite_channels

        if self._index is None or self._reader is None:
            return []

        level = (
            level_override
            if level_override is not None
            else self._pick_level(viewport, screen_width, screen_height)
        )

        x_min, y_min, x_max, y_max = viewport
        visible_fovs = self._index.query(x_min, y_min, x_max, y_max)

        vp_width_mm = max(x_max - x_min, 1e-6)
        mm_per_screen_px = vp_width_mm / max(screen_width, 1)
        target_tile_px = max(4, int(self._tile_w_mm / mm_per_screen_px))
        target_tile_px = min(target_tile_px, self._tile_w_px)

        ch_key = "_".join(str(c) for c in sorted(active_channels))
        screen_key = f"comp_{target_tile_px}_{ch_key}_{z}_{timepoint}_L{level}"
        cache_invalidated = screen_key != self._last_screen_key
        self._last_screen_key = screen_key

        tiles: list[VisibleTile] = []
        for fov in visible_fovs:
            display_key = f"disp_{fov.fov_index}_{screen_key}"

            if not cache_invalidated and display_key in self._display_cache:
                data = self._display_cache[display_key]
            else:
                # Load and downsample each active channel
                channel_data = []
                for ch_idx in active_channels:
                    raw = self._get_pyramid(fov.fov_index, z, ch_idx, timepoint, level)
                    processed = raw.astype(np.float32)
                    # Pipeline transforms (e.g. flatfield) operate on full-res
                    # maps. At pyramid level > 0 the frame is already a
                    # thumbnail; applying a full-res correction map here would
                    # crash on a shape mismatch. Defer processing to level 0;
                    # zoomed-out thumbnails show raw data.
                    if level == 0:
                        for transform in self._pipeline:
                            processed = transform(processed)
                    # For level 0, apply legacy screen-resolution downsampling;
                    # for level >= 1, the pyramid frame is already smaller.
                    if level == 0 and target_tile_px < self._tile_w_px:
                        factor = target_tile_px / self._tile_w_px
                        processed = ndi_zoom(processed, factor, order=0)

                    ch_name = channel_names[ch_idx] if ch_idx < len(channel_names) else ""
                    default_clim = (float(processed.min()), float(processed.max()))
                    clim = channel_clims.get(ch_idx, default_clim)
                    channel_data.append((processed, ch_name, clim))

                # Note: the compositor sums channel contributions and clips at [0, 1].
                # Heavy multi-channel regions may saturate; adjust clims to compensate.
                frames = [cd[0] for cd in channel_data]
                colors = [get_channel_rgb(cd[1]) for cd in channel_data]
                clims = [cd[2] for cd in channel_data]
                data = composite_channels(frames, clims, colors)
                self._display_cache[display_key] = data

            pos = self._position_overrides.get(fov.fov_index, (fov.x_mm, fov.y_mm))
            tiles.append(VisibleTile(
                fov_index=fov.fov_index,
                x_mm=pos[0], y_mm=pos[1],
                width_mm=self._tile_w_mm, height_mm=self._tile_h_mm,
                data=data,
            ))

        return tiles

    def all_fov_indices(self) -> set[int]:
        """All FOV indices in the currently loaded region."""
        if self._acquisition is None or self._region == "":
            return set()
        region_obj = self._acquisition.regions.get(self._region)
        if region_obj is None:
            return set()
        return {fov.fov_index for fov in region_obj.fovs}

    def get_volume(
        self,
        fov: int,
        channel: int,
        timepoint: int = 0,
        level: int = 0,
    ) -> np.ndarray:
        """Return the Z-stack for (fov, channel, timepoint) as (Z, Y, X)."""
        if self._acquisition is None:
            raise RuntimeError("No acquisition loaded")
        z_stack = self._acquisition.z_stack
        nz = z_stack.nz if z_stack else 1
        planes = [
            self._get_pyramid(fov, z, channel, timepoint, level)
            for z in range(nz)
        ]
        return np.stack(planes, axis=0)

    def all_volumes_for_region(
        self,
        channel: int,
        timepoint: int = 0,
        level: int = 0,
    ) -> dict[int, np.ndarray]:
        """Return {fov_index: volume} for every FOV in the current region."""
        return {
            fov_index: self.get_volume(fov_index, channel, timepoint, level)
            for fov_index in sorted(self.all_fov_indices())
        }

    def voxel_size_um(self) -> tuple[float, float, float]:
        """(vx, vy, vz) in micrometers — xy from the objective, z from z_stack."""
        xy = self.pixel_size_um
        if self._acquisition is None:
            return (xy, xy, xy)
        z_stack = self._acquisition.z_stack
        if z_stack is None or z_stack.nz <= 1:
            return (xy, xy, xy)
        return (xy, xy, z_stack.delta_z_mm * 1000.0)

    def visible_fov_indices(
        self, x_min: float, y_min: float, x_max: float, y_max: float,
    ) -> set[int]:
        """FOV indices whose tiles intersect the given viewport (mm)."""
        if self._index is None:
            return set()
        visible = self._index.query(x_min, y_min, x_max, y_max)
        return {fov.fov_index for fov in visible}

    def get_nominal_positions(
        self, indices: set[int],
    ) -> dict[int, tuple[float, float]]:
        """Return {fov_index: (x_mm, y_mm)} for the given indices.

        Returns nominal positions from coordinates.csv, ignoring any
        position overrides from registration.
        """
        if self._acquisition is None or self._region == "":
            return {}
        region_obj = self._acquisition.regions.get(self._region)
        if region_obj is None:
            return {}
        return {
            fov.fov_index: (fov.x_mm, fov.y_mm)
            for fov in region_obj.fovs
            if fov.fov_index in indices
        }

    def get_raw_frame(
        self, fov_index: int, z: int = 0, channel: int = 0, timepoint: int = 0,
    ) -> np.ndarray:
        """Get the raw (unprocessed) frame for a specific FOV."""
        return self._load_raw(fov_index, z, channel, timepoint)

    def _load_raw(self, fov: int, z: int, channel: int, timepoint: int) -> np.ndarray:
        """Load raw frame with caching."""
        cache_key = f"raw_{self._region}_{fov}_{z}_{channel}_{timepoint}"
        cached = self._raw_cache.get(cache_key)
        if cached is not None:
            return cached
        if self._reader is None:
            raise RuntimeError("No reader")
        key = FrameKey(region=self._region, fov=fov, z=z, channel=channel, timepoint=timepoint)
        frame = self._reader.read_frame(key)
        self._raw_cache.put(cache_key, frame)
        return frame

    def _get_pyramid(
        self, fov: int, z: int, channel: int, timepoint: int, level: int,
    ) -> np.ndarray:
        """Return the frame at the requested pyramid level (cached for level>=1)."""
        from squid_tools.viewer.pyramid import downsample_frame

        if level == 0:
            return self._load_raw(fov, z, channel, timepoint)
        key = (fov, z, channel, timepoint, level)
        cached = self._pyramid_cache.get(key)
        if cached is not None:
            return cached
        raw = self._load_raw(fov, z, channel, timepoint)
        levelled = downsample_frame(raw, level)
        self._pyramid_cache[key] = levelled
        return levelled

    def _pick_level(
        self,
        viewport: tuple[float, float, float, float],
        screen_width: int,
        screen_height: int,
    ) -> int:
        """Select pyramid level from viewport/screen mm-per-pixel ratio."""
        from squid_tools.viewer.pyramid import MAX_PYRAMID_LEVEL

        x_min, y_min, x_max, y_max = viewport
        if screen_width <= 0 or screen_height <= 0:
            return 0
        mm_per_px = max(
            (x_max - x_min) / max(screen_width, 1),
            (y_max - y_min) / max(screen_height, 1),
        )
        native_mm_per_px = self.pixel_size_um / 1000.0
        if native_mm_per_px <= 0 or mm_per_px <= 0:
            return 0
        ratio = int(mm_per_px / native_mm_per_px)
        if ratio < 2:
            return 0
        level = ratio.bit_length() - 1
        return min(level, MAX_PYRAMID_LEVEL)
