"""Multi-channel additive compositor (numpy + optional CuPy backend)."""

from __future__ import annotations

import enum
import logging
from collections.abc import Sequence

import numpy as np

logger = logging.getLogger(__name__)


class Backend(enum.Enum):
    NUMPY = "numpy"
    CUPY = "cupy"


def _select_backend() -> Backend:
    try:
        import cupy as cp  # type: ignore[import-not-found]

        a = cp.asarray(np.zeros((2, 2), dtype=np.float32))
        _ = float(a.sum())
        return Backend.CUPY
    except Exception:
        return Backend.NUMPY


DEFAULT_BACKEND = _select_backend()
logger.info("compositor backend: %s", DEFAULT_BACKEND.value)

_warned_cupy_failure = False


def composite_channels(
    frames: Sequence[np.ndarray],
    clims: Sequence[tuple[float, float]],
    colors_rgb: Sequence[tuple[float, float, float]],
    backend: Backend | None = None,
) -> np.ndarray:
    """Composite N grayscale channels into a (H, W, 3) float32 RGB array.

    For each channel:
      normalized = clip((frame - lo) / (hi - lo), 0, 1)
      contribution = normalized * color_rgb
    Output is the sum over all channels, clipped to [0, 1].
    """
    if not (len(frames) == len(clims) == len(colors_rgb)):
        raise ValueError("frames, clims, colors_rgb must be same length")
    if len(frames) == 0:
        raise ValueError("at least one channel required")
    for f in frames:
        if f.ndim != 2:
            raise ValueError(f"frames must be 2D, got {f.ndim}D")
    h, w = frames[0].shape
    for f in frames[1:]:
        if f.shape != (h, w):
            raise ValueError("all frames must have the same shape")

    chosen = backend if backend is not None else DEFAULT_BACKEND
    if chosen is Backend.CUPY:
        try:
            return _composite_cupy(frames, clims, colors_rgb)
        except Exception:
            global _warned_cupy_failure
            if not _warned_cupy_failure:
                logger.warning(
                    "CuPy compositing failed; falling back to numpy",
                    exc_info=True,
                )
                _warned_cupy_failure = True
    return _composite_numpy(frames, clims, colors_rgb)


def _composite_numpy(
    frames: Sequence[np.ndarray],
    clims: Sequence[tuple[float, float]],
    colors_rgb: Sequence[tuple[float, float, float]],
) -> np.ndarray:
    h, w = frames[0].shape
    out = np.zeros((h, w, 3), dtype=np.float32)
    for frame, (lo, hi), color in zip(frames, clims, colors_rgb, strict=True):
        denom = max(hi - lo, 1e-6)
        normed = np.clip((frame.astype(np.float32) - lo) / denom, 0.0, 1.0)
        out += normed[..., None] * np.asarray(color, dtype=np.float32)
    np.clip(out, 0.0, 1.0, out=out)
    return out


def _composite_cupy(
    frames: Sequence[np.ndarray],
    clims: Sequence[tuple[float, float]],
    colors_rgb: Sequence[tuple[float, float, float]],
) -> np.ndarray:
    import cupy as cp  # type: ignore[import-not-found]

    h, w = frames[0].shape
    out = cp.zeros((h, w, 3), dtype=cp.float32)
    for frame, (lo, hi), color in zip(frames, clims, colors_rgb, strict=True):
        denom = max(hi - lo, 1e-6)
        gpu_frame = cp.asarray(frame, dtype=cp.float32)
        normed = cp.clip((gpu_frame - lo) / denom, 0.0, 1.0)
        color_arr = cp.asarray(color, dtype=cp.float32)
        out += normed[..., None] * color_arr
    out = cp.clip(out, 0.0, 1.0)
    return cp.asnumpy(out).astype(np.float32)


def composite_volume_channels(
    volumes: Sequence[np.ndarray],
    clims: Sequence[tuple[float, float]],
    colors_rgb: Sequence[tuple[float, float, float]],
    backend: Backend | None = None,
) -> np.ndarray:
    """Composite N 3D grayscale volumes into (Z, Y, X, 4) float32 RGBA.

    RGB: sum of color * normalized contributions, clipped to [0, 1].
    Alpha: per-voxel max of normalized values across channels, so
    voxels with no signal stay transparent in ray-marched rendering.

    The `backend` parameter is reserved; this cycle is numpy-only.
    """
    if not (len(volumes) == len(clims) == len(colors_rgb)):
        raise ValueError("volumes, clims, colors_rgb must be same length")
    if len(volumes) == 0:
        raise ValueError("at least one channel required")
    for v in volumes:
        if v.ndim != 3:
            raise ValueError(f"volumes must be 3D (Z,Y,X), got {v.ndim}D")
    shape = volumes[0].shape
    for v in volumes[1:]:
        if v.shape != shape:
            raise ValueError("all volumes must have the same shape")

    z, h, w = shape
    rgb = np.zeros((z, h, w, 3), dtype=np.float32)
    alpha = np.zeros((z, h, w), dtype=np.float32)
    for volume, (lo, hi), color in zip(volumes, clims, colors_rgb, strict=True):
        denom = max(hi - lo, 1e-6)
        normed = np.clip((volume.astype(np.float32) - lo) / denom, 0.0, 1.0)
        rgb += normed[..., None] * np.asarray(color, dtype=np.float32)
        np.maximum(alpha, normed, out=alpha)
    np.clip(rgb, 0.0, 1.0, out=rgb)
    out = np.empty((z, h, w, 4), dtype=np.float32)
    out[..., :3] = rgb
    out[..., 3] = alpha
    logger.info(
        "volume composited: %s from %d channels", out.shape, len(volumes),
    )
    return out
