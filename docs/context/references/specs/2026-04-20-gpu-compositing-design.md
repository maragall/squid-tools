# GPU Compositing Design Spec

## Purpose

Multi-channel additive compositing today runs on the CPU: numpy multiplies each grayscale channel by its color, adds, and clips. For 8+ channels at full resolution this is measurable (10s of ms per tile × dozens of tiles). This cycle introduces a compositor abstraction that runs on CuPy when available (Linux / Windows with NVIDIA GPUs), and falls back to numpy everywhere else (macOS, CUDA-less Linux/Windows).

**Audience:** Users with heavy multi-channel data (8+ channels) on supported hardware. Invisible to users without GPUs (they continue to use the numpy path).

**Guiding principle:** One compositor API, two backends. The caller doesn't know (or care) which backend ran. If CuPy is missing or fails at runtime, the numpy backend is used — the app never crashes because of a GPU issue.

---

## Scope

**IN:**
- `squid_tools/viewer/compositor.py` with:
  - `composite_channels(frames, clims, colors_rgb) -> np.ndarray` (RGB float32 HxWx3, 0..1)
  - `Backend` enum: `NUMPY`, `CUPY`
  - `DEFAULT_BACKEND` constant auto-selected once per process at import
  - Private `_composite_numpy` and `_composite_cupy` implementations
- `ViewportEngine` uses `composite_channels` in `get_composite_tiles` instead of the inline numpy composite
- Runtime backend selection: on import, try `import cupy` + do a trivial 2x2 composite to verify the GPU works; cache result as `DEFAULT_BACKEND`
- `composite_channels` accepts an optional `backend: Backend | None` for tests/manual override (defaults to `DEFAULT_BACKEND`)
- CuPy failures at runtime fall back to numpy for that call and log a WARNING (once, deduplicated)
- No new dependencies declared in `squid_tools/viewer/pyproject.toml` — `cupy` is optional (`try: import cupy`)

**OUT (future cycles):**
- WebGL / WebGPU backend (for the browser demo — Cycle G)
- Per-channel gamma correction
- HDR tone mapping
- LUT cache on device (re-upload per frame for this cycle)
- Compute-shader compositing (GLSL) — we use CuPy array ops, not custom kernels

---

## Architecture

```
ViewportEngine.get_composite_tiles
   |
   | for each visible FOV:
   |   frames = [self._get_pyramid(fov, z, ch, t, level) for ch in active_channels]
   |   clims  = [channel_clims[ch] for ch in active_channels]
   |   colors = [channel_rgb(ch_name) for ch_name in channel_names]
   |   rgb = composite_channels(frames, clims, colors)
   |
   v
composite_channels(frames, clims, colors)
   |
   | backend = chosen_backend
   |
   +-> NUMPY: multiply each frame by color, add, clip to [0,1]
   |
   +-> CUPY: move arrays to GPU, same op, copy back to CPU
```

Backend selection at import time:

```python
def _select_backend() -> Backend:
    try:
        import cupy as cp
        a = cp.asarray(np.zeros((2, 2), dtype=np.float32))
        _ = float(a.sum())  # trigger kernel to verify device works
        return Backend.CUPY
    except Exception:
        return Backend.NUMPY
```

One-shot at import. No per-call probing.

---

## Components

### 1. `squid_tools/viewer/compositor.py`

```python
"""Multi-channel additive compositor (numpy + optional CuPy backend)."""

from __future__ import annotations

import enum
import logging
from typing import Sequence

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
_warned_cupy_failure = False


def composite_channels(
    frames: Sequence[np.ndarray],
    clims: Sequence[tuple[float, float]],
    colors_rgb: Sequence[tuple[float, float, float]],
    backend: Backend | None = None,
) -> np.ndarray:
    """Composite N grayscale channels into an RGB frame.

    For each channel:
      normalized = (frame - clim_lo) / (clim_hi - clim_lo)  clipped to [0, 1]
      contribution = normalized[..., None] * color_rgb[None, None, :]
    Output = sum of contributions, clipped to [0, 1].

    Returns float32 array of shape (H, W, 3).

    Raises ValueError if lengths mismatch or frames are not 2D.
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
```

### 2. `ViewportEngine` changes

- In `get_composite_tiles`, replace the inline per-channel compositing with a single call to `composite_channels(frames, clims, colors_rgb)`.
- `colors_rgb` list is built from the existing `get_channel_rgb(channel_name)` helper (or whatever color-lookup function the viewer uses) — values in 0..1.
- Keep all pyramid, clims, and tile-position logic unchanged. Only the compositing loop is swapped for the new call.

---

## Error Handling

| Failure | Behavior |
|---------|----------|
| `cupy` not installed | Selection falls to `Backend.NUMPY` at import time. |
| CuPy import succeeds but GPU is unavailable at runtime | `_composite_cupy` raises; caller catches, logs WARNING once, uses numpy. |
| Frames have different shapes | `composite_channels` raises `ValueError` (defensive). |
| Frames is empty | `composite_channels` raises `ValueError`. |
| A clim has `lo == hi` | Treated as `hi = lo + 1e-6` to avoid division by zero. Channel appears uniformly at its bottom. |

---

## UX Details

No visible UI change. Users with CuPy installed get faster composite; everyone else sees identical output.

Log output at INFO on app start:
```
[14:23:00] [INFO] [viewer] compositor backend: numpy
```

or:
```
[14:23:00] [INFO] [viewer] compositor backend: cupy
```

(Emitted once from the compositor module at import, after `_select_backend()`.)

---

## Testing Plan

**(Written at end of all cycles — functional user workflow tests for the complete integrated product. Per-cycle TDD is handled by superpowers during implementation.)**

Placeholder: this cycle's TDD tests live in its implementation plan. The spec's Testing Plan section will be written when all planned cycles are complete, describing end-to-end user workflows to validate the full product.
