"""Image pyramid utilities: 2x decimation per level."""

from __future__ import annotations

import numpy as np

MAX_PYRAMID_LEVEL = 5


def downsample_frame(frame: np.ndarray, level: int) -> np.ndarray:
    """Decimate frame by 2**level via stride slicing.

    level=0 returns the original frame unchanged (no copy).
    level>=1 returns a contiguous copy decimated by 2**level on the YX axes.
    Accepts 2D (YX) or 3D (CYX) arrays.
    """
    if level < 0:
        raise ValueError(f"level must be >= 0, got {level}")
    if frame.ndim not in (2, 3):
        raise ValueError(f"frame must be 2D or 3D, got {frame.ndim}D")
    if level == 0:
        return frame
    step = 1 << level
    if frame.ndim == 2:
        return frame[::step, ::step].copy()
    return frame[:, ::step, ::step].copy()
