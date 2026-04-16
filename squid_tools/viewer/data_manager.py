"""Data-intensive viewport data manager.

Handles: thumbnail generation, viewport-aware tile loading,
processing pipeline application, global contrast normalization.
Knows nothing about OpenGL or Qt.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
from scipy.ndimage import zoom as ndi_zoom

from squid_tools.core.cache import MemoryBoundedLRUCache
from squid_tools.core.data_model import Acquisition, FrameKey
from squid_tools.core.readers import detect_reader
from squid_tools.core.readers.base import FormatReader

THUMBNAIL_SIZE = 256


class ViewportDataManager:
    """Brain of the viewer. Manages all data flow from disk to canvas."""

    def __init__(self, cache_bytes: int = 256 * 1024 * 1024) -> None:
        self.acquisition: Acquisition | None = None
        self._reader: FormatReader | None = None
        self._raw_cache = MemoryBoundedLRUCache(max_bytes=cache_bytes)
        self._thumb_cache: dict[str, np.ndarray] = {}
        self._contrast_cache: dict[str, tuple[float, float]] = {}
        self._pipeline: list[Callable[[np.ndarray], np.ndarray]] = []

    def load(self, path: Path) -> Acquisition:
        """Load an acquisition directory."""
        self._reader = detect_reader(path)
        self.acquisition = self._reader.read_metadata(path)
        self._raw_cache.clear()
        self._thumb_cache.clear()
        self._contrast_cache.clear()
        return self.acquisition

    @property
    def pixel_size_um(self) -> float:
        if self.acquisition is None:
            raise RuntimeError("No acquisition loaded")
        return self.acquisition.objective.pixel_size_um

    def region_ids(self) -> list[str]:
        if self.acquisition is None:
            return []
        return list(self.acquisition.regions.keys())

    # --- Raw frame access (cached) ---

    def get_raw_frame(
        self,
        region: str,
        fov: int,
        z: int = 0,
        channel: int = 0,
        timepoint: int = 0,
    ) -> np.ndarray:
        """Load raw frame from disk with caching. No pipeline applied."""
        if self._reader is None:
            raise RuntimeError("No acquisition loaded")
        cache_key = f"raw_{region}_{fov}_{z}_{channel}_{timepoint}"
        cached = self._raw_cache.get(cache_key)
        if cached is not None:
            return cached
        key = FrameKey(region=region, fov=fov, z=z, channel=channel, timepoint=timepoint)
        frame = self._reader.read_frame(key)
        self._raw_cache.put(cache_key, frame)
        return frame

    def get_frame(
        self,
        region: str,
        fov: int,
        z: int = 0,
        channel: int = 0,
        timepoint: int = 0,
    ) -> np.ndarray:
        """Load frame with processing pipeline applied.

        If no pipeline is set, returns the cached raw frame (same object).
        """
        raw = self.get_raw_frame(region, fov, z, channel, timepoint)
        if not self._pipeline:
            return raw
        result = raw.astype(np.float32)
        for transform in self._pipeline:
            result = transform(result)
        return result

    def get_region_frames(
        self,
        region: str,
        z: int = 0,
        channel: int = 0,
        timepoint: int = 0,
    ) -> dict[int, np.ndarray]:
        """Load all FOV frames for a region (with pipeline)."""
        if self.acquisition is None:
            raise RuntimeError("No acquisition loaded")
        if region not in self.acquisition.regions:
            raise ValueError(f"Region '{region}' not found")
        frames: dict[int, np.ndarray] = {}
        for fov in self.acquisition.regions[region].fovs:
            frames[fov.fov_index] = self.get_frame(region, fov.fov_index, z, channel, timepoint)
        return frames

    # --- Pipeline (toggle-based) ---

    def set_pipeline(self, transforms: list[Callable[[np.ndarray], np.ndarray]]) -> None:
        """Set the active processing pipeline. Empty list = raw data."""
        self._pipeline = transforms

    # --- Thumbnails ---

    def get_thumbnail(
        self,
        region: str,
        fov: int,
        channel: int = 0,
        z: int = 0,
        timepoint: int = 0,
    ) -> np.ndarray:
        """Get or generate a thumbnail for a tile."""
        thumb_key = f"thumb_{region}_{fov}_{channel}_{z}_{timepoint}"
        if thumb_key in self._thumb_cache:
            return self._thumb_cache[thumb_key]

        frame = self.get_frame(region, fov, z, channel, timepoint)
        h, w = frame.shape[:2]
        factor = min(THUMBNAIL_SIZE / h, THUMBNAIL_SIZE / w)
        if factor < 1.0:
            thumb = ndi_zoom(frame.astype(np.float32), factor, order=0)
        else:
            thumb = frame.astype(np.float32)
        self._thumb_cache[thumb_key] = thumb
        return thumb

    def get_region_thumbnails(
        self,
        region: str,
        channel: int = 0,
        z: int = 0,
        timepoint: int = 0,
    ) -> dict[int, np.ndarray]:
        """Get thumbnails for all FOVs in a region."""
        if self.acquisition is None:
            raise RuntimeError("No acquisition loaded")
        thumbs: dict[int, np.ndarray] = {}
        for fov in self.acquisition.regions[region].fovs:
            thumbs[fov.fov_index] = self.get_thumbnail(
                region, fov.fov_index, channel, z, timepoint
            )
        return thumbs

    def invalidate_thumbnails(self) -> None:
        """Clear thumbnail cache (call when pipeline changes)."""
        self._thumb_cache.clear()

    # --- Contrast normalization ---

    def get_contrast_stats(
        self,
        region: str,
        channel: int = 0,
        z: int = 0,
        timepoint: int = 0,
        sample_every: int = 5,
    ) -> tuple[float, float]:
        """Compute global p1/p99 contrast stats across tiles in a region.

        Samples every Nth tile to avoid loading everything.
        """
        stats_key = f"contrast_{region}_{channel}_{z}_{timepoint}"
        if stats_key in self._contrast_cache:
            return self._contrast_cache[stats_key]

        if self.acquisition is None:
            raise RuntimeError("No acquisition loaded")

        fovs = self.acquisition.regions[region].fovs
        sampled_pixels: list[np.ndarray] = []
        for i, fov in enumerate(fovs):
            if i % sample_every != 0:
                continue
            frame = self.get_raw_frame(region, fov.fov_index, z, channel, timepoint)
            # Sample 1000 random pixels to keep it fast
            flat = frame.ravel()
            if len(flat) > 1000:
                indices = np.random.default_rng(42).choice(len(flat), 1000, replace=False)
                sampled_pixels.append(flat[indices])
            else:
                sampled_pixels.append(flat)

        all_pixels = np.concatenate(sampled_pixels)
        p1 = float(np.percentile(all_pixels, 1))
        p99 = float(np.percentile(all_pixels, 99))
        if p1 == p99:
            p99 = p1 + 1.0

        self._contrast_cache[stats_key] = (p1, p99)
        return p1, p99

    # --- Viewport-aware loading ---

    def get_tile_size_mm(self, region: str) -> tuple[float, float]:
        """Get tile size in mm for a region (from first FOV frame)."""
        if self.acquisition is None:
            raise RuntimeError("No acquisition loaded")
        region_obj = self.acquisition.regions.get(region)
        if not region_obj or not region_obj.fovs:
            return (0.0, 0.0)
        first_fov = region_obj.fovs[0]
        frame = self.get_raw_frame(region, first_fov.fov_index)
        h_px, w_px = frame.shape[:2]
        pixel_size = self.pixel_size_um
        return (w_px * pixel_size / 1000, h_px * pixel_size / 1000)

    def get_visible_fov_indices(
        self,
        region: str,
        viewport: tuple[float, float, float, float],
    ) -> list[int]:
        """Return FOV indices whose tiles intersect the viewport.

        Args:
            viewport: (x_min, y_min, x_max, y_max) in mm (stage coordinates).
        """
        if self.acquisition is None:
            return []

        region_obj = self.acquisition.regions.get(region)
        if region_obj is None:
            return []

        vx_min, vy_min, vx_max, vy_max = viewport
        visible: list[int] = []

        # Tile size in mm
        tile_w_mm, tile_h_mm = self.get_tile_size_mm(region)
        if tile_w_mm == 0:
            return []

        for fov in region_obj.fovs:
            # Tile bounds in mm
            tx_min, ty_min = fov.x_mm, fov.y_mm
            tx_max = fov.x_mm + tile_w_mm
            ty_max = fov.y_mm + tile_h_mm

            # Check intersection with viewport (mm)
            if tx_max > vx_min and tx_min < vx_max and ty_max > vy_min and ty_min < vy_max:
                visible.append(fov.fov_index)

        return visible
