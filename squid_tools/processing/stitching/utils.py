"""GPU/CPU detection and array utilities for stitching.

Absorbed from TileFusion. Provides a unified `xp` namespace
(cupy when GPU available, numpy otherwise) and wrapper functions
for registration operations.
"""

import numpy as np

try:
    import cupy as cp
    from cucim.skimage.exposure import match_histograms
    from cucim.skimage.measure import block_reduce
    from cucim.skimage.registration import phase_cross_correlation
    from cupyx.scipy.ndimage import shift as cp_shift

    xp = cp
    USING_GPU = True
except Exception:
    cp = None
    cp_shift = None
    from scipy.ndimage import shift as _shift_cpu
    from skimage.exposure import match_histograms  # type: ignore[no-redef]  # noqa: F401
    from skimage.measure import block_reduce  # type: ignore[no-redef]  # noqa: F401
    from skimage.registration import phase_cross_correlation  # type: ignore[no-redef]  # noqa: F401

    xp = np  # type: ignore[assignment]
    USING_GPU = False


def shift_array(arr: np.ndarray, shift_vec: tuple | np.ndarray) -> np.ndarray:
    """Shift array using GPU if available, else CPU."""
    if USING_GPU and cp_shift is not None:
        return cp_shift(arr, shift=shift_vec, order=1, prefilter=False)  # type: ignore[no-any-return]
    return _shift_cpu(arr, shift=shift_vec, order=1, prefilter=False)


def compute_ssim(arr1: np.ndarray, arr2: np.ndarray, win_size: int) -> float:
    """SSIM between two 2D arrays."""
    from skimage.metrics import structural_similarity

    a1 = np.asarray(arr1)
    a2 = np.asarray(arr2)
    data_range = float(a1.max() - a1.min())
    if data_range == 0:
        data_range = 1.0
    return float(structural_similarity(a1, a2, win_size=win_size, data_range=data_range))


def make_1d_profile(length: int, blend: int) -> np.ndarray:
    """Linear ramp profile for feather blending."""
    blend = min(blend, length // 2)
    prof = np.ones(length, dtype=np.float32)
    if blend > 0:
        ramp = np.linspace(0, 1, blend, endpoint=False, dtype=np.float32)
        prof[:blend] = ramp
        prof[-blend:] = ramp[::-1]
    return prof


def to_numpy(arr: np.ndarray) -> np.ndarray:
    """Convert to numpy, handling both CPU and GPU arrays."""
    if USING_GPU and cp is not None and isinstance(arr, cp.ndarray):
        return cp.asnumpy(arr)
    return np.asarray(arr)


def to_device(arr: np.ndarray) -> np.ndarray:
    """Move array to current device."""
    return xp.asarray(arr)  # type: ignore[no-any-return]
