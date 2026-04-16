"""
Tile fusion algorithms.

Numba-accelerated weighted blending and accumulation kernels.
"""

import numpy as np
from numba import njit, prange


@njit(parallel=True)
def accumulate_tile_shard(
    fused: np.ndarray,
    weight: np.ndarray,
    sub: np.ndarray,
    w2d: np.ndarray,
    y_off: int,
    x_off: int,
) -> None:
    """
    Weighted accumulation of a 2D sub-tile into the fused buffer.

    Parameters
    ----------
    fused : float32[C, Y, X]
        Accumulation buffer.
    weight : float32[C, Y, X]
        Weight accumulation buffer.
    sub : float32[C, Y, X]
        Sub-tile to blend.
    w2d : float32[Y, X]
        Weight profile.
    y_off, x_off : int
        Offsets of sub-tile in the fused volume.
    """
    n_c, yp, xp = fused.shape  # noqa: N806
    _, sub_y, sub_x = sub.shape  # noqa: N806
    total = sub_y * sub_x

    for idx in prange(total):
        y_i = idx // sub_x
        x_i = idx % sub_x
        gy = y_off + y_i
        gx = x_off + x_i
        if gy < 0 or gy >= yp or gx < 0 or gx >= xp:
            continue
        w_val = w2d[y_i, x_i]
        for c in range(n_c):
            fused[c, gy, gx] += sub[c, y_i, x_i] * w_val
            weight[c, gy, gx] += w_val


@njit(parallel=True)
def normalize_shard(fused: np.ndarray, weight: np.ndarray) -> None:
    """
    Normalize the fused buffer by its weight buffer, in-place.

    Parameters
    ----------
    fused : float32[C, Y, X]
        Accumulation buffer to normalize.
    weight : float32[C, Y, X]
        Corresponding weights.
    """
    n_c, yp, xp = fused.shape  # noqa: N806
    total = n_c * yp * xp

    for idx in prange(total):
        c = idx // (yp * xp)
        rem = idx % (yp * xp)
        y_i = rem // xp
        x_i = rem % xp
        w_val = weight[c, y_i, x_i]
        fused[c, y_i, x_i] = fused[c, y_i, x_i] / w_val if w_val > 0 else 0.0


@njit(parallel=True)
def blend_numba_2d(
    sub_i: np.ndarray,
    sub_j: np.ndarray,
    wy_i: np.ndarray,
    wx_i: np.ndarray,
    wy_j: np.ndarray,
    wx_j: np.ndarray,
    out_f: np.ndarray,
) -> np.ndarray:
    """
    Feather-blend two overlapping 2D sub-tiles.

    Parameters
    ----------
    sub_i, sub_j : (dy, dx) float32
        Input sub-tiles.
    wy_i, wx_i : 1D float32
        Weight profiles for sub_i.
    wy_j, wx_j : 1D float32
        Weight profiles for sub_j.
    out_f : (dy, dx) float32
        Pre-allocated output buffer.

    Returns
    -------
    out_f : (dy, dx) float32
        Blended result.
    """
    dy, dx = sub_i.shape

    for y in prange(dy):
        wi_y = wy_i[y]
        wj_y = wy_j[y]
        for x in range(dx):
            wi = wi_y * wx_i[x]
            wj = wj_y * wx_j[x]
            tot = wi + wj
            if tot > 1e-6:
                out_f[y, x] = (wi * sub_i[y, x] + wj * sub_j[y, x]) / tot
            else:
                out_f[y, x] = sub_i[y, x]
    return out_f
