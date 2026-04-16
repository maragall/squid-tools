"""Flatfield correction algorithms.

Provides BaSiCPy-based correction when available, with a simple
mean-based fallback. Absorbed from TileFusion flatfield module.
"""

from __future__ import annotations

import numpy as np

try:
    from basicpy import BaSiC

    HAS_BASICPY = True
except ImportError:
    HAS_BASICPY = False


def calculate_flatfield(
    tiles: list[np.ndarray],
    use_darkfield: bool = False,
) -> tuple[np.ndarray, np.ndarray | None]:
    """Calculate flatfield using BaSiCPy if available, else simple mean.

    Parameters
    ----------
    tiles : list of 2D arrays
        Collection of tile images for flatfield estimation.
    use_darkfield : bool
        Whether to compute darkfield correction.

    Returns
    -------
    flatfield : ndarray (Y, X) float32
    darkfield : ndarray or None
    """
    if HAS_BASICPY:
        basic = BaSiC(get_darkfield=use_darkfield)
        stack = np.stack(tiles)
        basic.fit(stack)
        flatfield = basic.flatfield.astype(np.float32)
        darkfield = basic.darkfield.astype(np.float32) if use_darkfield else None
        return flatfield, darkfield

    return calculate_flatfield_simple(tiles), None


def calculate_flatfield_simple(tiles: list[np.ndarray]) -> np.ndarray:
    """Simple flatfield estimation: mean of all tiles, normalized.

    Fallback when BaSiCPy is not installed.
    """
    stack = np.stack([t.astype(np.float32) for t in tiles])
    mean_image = np.mean(stack, axis=0)
    mean_val = np.mean(mean_image)
    if mean_val > 0:
        return (mean_image / mean_val).astype(np.float32)
    return np.ones_like(mean_image, dtype=np.float32)


def apply_flatfield(
    image: np.ndarray,
    flatfield: np.ndarray,
    darkfield: np.ndarray | None = None,
) -> np.ndarray:
    """Apply flatfield (and optional darkfield) correction.

    corrected = (image - darkfield) / flatfield
    """
    result = image.astype(np.float32)
    if darkfield is not None:
        result = result - darkfield.astype(np.float32)

    # Normalize flatfield to mean 1
    flat = flatfield.astype(np.float32)
    flat_mean = np.mean(flat)
    if flat_mean > 0:
        flat = flat / flat_mean

    # Avoid division by zero
    flat = np.where(flat > 0.01, flat, 1.0)
    return result / flat
