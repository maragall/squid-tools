# Multi-scale Pyramid Zoom Design Spec

## Purpose

When the user zooms out over a large mosaic (hundreds of FOVs), rendering each FOV at full resolution is wasteful: every FOV maps to only a few pixels on screen, but the engine still reads the full-res tile from disk and composites it. A pyramid caches downsampled versions of each frame, and the engine picks the level that matches the current zoom.

This cycle adds level-aware tile fetching to `ViewportEngine`. The GUI doesn't change — `get_composite_tiles` transparently picks the right level based on the viewport/screen ratio.

**Audience:** Users with 500+ FOV mosaics (e.g., whole-slide scans) who currently see multi-second stalls on zoom-out. Also prerequisite for Cycle E (3D rendering) — 3D volumes need pyramids for real-time frustum updates.

**Guiding principle:** The pyramid is a render-time optimization, not a new data model. A frame is one frame; it has multiple resolutions. Level 0 is canonical; higher levels are computed (cached) copies.

---

## Scope

**IN:**
- `squid_tools/viewer/pyramid.py` with `downsample_frame(frame, level)` (2x decimation per level, via numpy striding — fast, no SciPy required)
- `ViewportEngine._pyramid_cache: dict[tuple[int, int, int, int, int], np.ndarray]` keyed by `(fov, z, channel, t, level)`
- `ViewportEngine._pick_level(viewport_mm, screen_px) -> int` — selects the pyramid level whose downsampled pixel size matches ~1 screen pixel per image pixel
- `ViewportEngine.get_composite_tiles` passes the selected level through to `_load_raw` so tiles come back at the right resolution
- `get_composite_tiles` accepts an optional `level_override: int | None` for tests / manual control
- Pyramid levels capped at `MAX_PYRAMID_LEVEL = 5` (1/32 resolution); beyond that, always return level 5
- Level-0 behavior unchanged: a level-0 request goes straight to the reader with no downsample

**OUT (future cycles):**
- Disk-backed pyramid (`.squid-tools/pyramid/…`). This cycle keeps everything in RAM-bounded LRU.
- Pyramid building on GPU (CuPy). Numpy downsample is cheap enough.
- Interpolation choice (we use `[::2, ::2]` slicing — fast, adequate for thumbnails; Lanczos / bicubic would be a later polish)
- Per-channel pyramid variations. One pyramid per (fov, z, c, t); level applies uniformly.
- Pyramid metadata in the OME sidecar.

---

## Architecture

```
get_composite_tiles(viewport, screen_w, screen_h, ...)
    |
    v
level = self._pick_level(viewport, screen_w, screen_h)   # 0-5
    |
    v
for each visible fov:
    for each active channel:
        frame = self._get_pyramid(fov, z, channel, t, level)
            |
            +-- cache hit: return cached np.ndarray
            |
            +-- cache miss:
                    raw = self._load_raw(fov, z, channel, t)   # level 0
                    levelled = downsample_frame(raw, level)     # numpy stride
                    self._pyramid_cache[key] = levelled
                    return levelled
    composite the (fov, channel_stack) at this level
```

`_pick_level` heuristic:

```python
def _pick_level(self, viewport_mm, screen_w, screen_h) -> int:
    x_min, y_min, x_max, y_max = viewport_mm
    mm_per_px = max((x_max - x_min) / screen_w, (y_max - y_min) / screen_h)
    native_mm_per_px = self.pixel_size_um() / 1000.0
    if native_mm_per_px <= 0:
        return 0
    ratio = mm_per_px / native_mm_per_px
    # ratio >= 2 means we're rendering 2 native pixels per screen pixel → use level 1
    level = max(0, int(ratio).bit_length() - 1)
    return min(level, MAX_PYRAMID_LEVEL)
```

The `.bit_length() - 1` gives `floor(log2(ratio))`: at ratio=1 → 0, ratio=2 → 1, ratio=4 → 2, etc. Integer-only arithmetic; no log/floor imports.

---

## Components

### 1. `squid_tools/viewer/pyramid.py`

```python
"""Image pyramid utilities: 2x decimation per level."""

from __future__ import annotations

import numpy as np

MAX_PYRAMID_LEVEL = 5


def downsample_frame(frame: np.ndarray, level: int) -> np.ndarray:
    """Decimate frame by 2**level via stride slicing.

    level=0 returns the original frame unchanged.
    level=1 returns every other row/column (1/2 size).
    level=2 returns every fourth row/column (1/4 size), etc.

    Raises ValueError if level < 0 or frame is not 2D (YX) or 3D (CYX).
    """
    if level < 0:
        raise ValueError(f"level must be >= 0, got {level}")
    if frame.ndim not in (2, 3):
        raise ValueError(f"frame must be 2D or 3D, got {frame.ndim}D")
    if level == 0:
        return frame
    step = 1 << level  # 2**level via bit shift
    if frame.ndim == 2:
        return frame[::step, ::step].copy()
    return frame[:, ::step, ::step].copy()
```

### 2. `ViewportEngine` changes

Add:
```python
_pyramid_cache: dict[tuple[int, int, int, int, int], np.ndarray]
```
initialized to `{}` in `__init__`. Cleared when a new acquisition is loaded. Not LRU-bounded this cycle — small footprint because downsampled frames are tiny; revisit if profiling shows bloat.

New method:
```python
def _pick_level(
    self, viewport: tuple[float, float, float, float],
    screen_width: int, screen_height: int,
) -> int:
    from squid_tools.viewer.pyramid import MAX_PYRAMID_LEVEL
    x_min, y_min, x_max, y_max = viewport
    if screen_width <= 0 or screen_height <= 0:
        return 0
    mm_per_px = max(
        (x_max - x_min) / max(screen_width, 1),
        (y_max - y_min) / max(screen_height, 1),
    )
    native_mm_per_px = self.pixel_size_um() / 1000.0
    if native_mm_per_px <= 0 or mm_per_px <= 0:
        return 0
    ratio = int(mm_per_px / native_mm_per_px)
    if ratio < 2:
        return 0
    level = ratio.bit_length() - 1
    return min(level, MAX_PYRAMID_LEVEL)


def _get_pyramid(
    self, fov: int, z: int, channel: int, timepoint: int, level: int,
) -> np.ndarray:
    """Return the frame at the requested pyramid level (cached)."""
    from squid_tools.viewer.pyramid import downsample_frame
    key = (fov, z, channel, timepoint, level)
    cached = self._pyramid_cache.get(key)
    if cached is not None:
        return cached
    raw = self._load_raw(fov, z, channel, timepoint)
    levelled = downsample_frame(raw, level) if level > 0 else raw
    if level > 0:
        self._pyramid_cache[key] = levelled
    return levelled
```

`get_composite_tiles` changes:
- Accept a keyword-only `level_override: int | None = None`
- Compute `level = level_override if level_override is not None else self._pick_level(viewport, screen_width, screen_height)`
- When fetching each tile's frame, call `self._get_pyramid(fov, z, channel, t, level)` instead of `self._load_raw(...)`

The returned tile's `width_mm`, `height_mm`, `x_mm`, `y_mm` remain the same (they describe physical space, not pixel count). The canvas uploads the smaller texture; OpenGL takes care of scaling it to the same physical footprint.

---

## Data Flow

1. Widget calls `get_composite_tiles(viewport, screen_w, screen_h, ...)` (synchronous path unchanged).
2. Engine picks level = N based on viewport/screen ratio.
3. For each FOV, engine fetches the level-N frame (computing + caching if first access).
4. Engine composites the level-N frames as usual (per-channel blending identical).
5. Canvas uploads the smaller texture, GPU upscales to physical footprint.

At level 0, behavior is exactly as before (no downsample, no cache entry).

---

## Error Handling

| Failure | Behavior |
|---------|----------|
| Frame read fails (reader raises) | Propagated as before. No cache entry created. |
| Downsample produces empty array (very small frame + high level) | `downsample_frame` returns whatever stride slicing gives (possibly `(0, 0)`); caller handles empty. Not observed in practice because `MAX_PYRAMID_LEVEL = 5` limits this. |
| `screen_width == 0` (viewport has no rendering surface) | `_pick_level` returns 0; `get_composite_tiles` already early-returns on zero size. |
| `pixel_size_um()` returns 0 or negative | `_pick_level` returns 0. |

---

## UX Details

No visible UI change. User perceives faster zoom-out.

Log output (DEBUG):
```
[14:23:10] [DEBUG] [viewer] pyramid level=2 for viewport=(0.0, 0.0, 10.0, 8.0), screen=1920x1080
[14:23:10] [DEBUG] [viewer] pyramid cache hit fov=5 z=0 ch=0 t=0 level=2
[14:23:10] [DEBUG] [viewer] pyramid cache miss fov=12 z=0 ch=0 t=0 level=2, downsampling
```

---

## Testing Plan

**(Written at end of all cycles — functional user workflow tests for the complete integrated product. Per-cycle TDD is handled by superpowers during implementation.)**

Placeholder: this cycle's TDD tests live in its implementation plan. The spec's Testing Plan section will be written when all planned cycles are complete, describing end-to-end user workflows to validate the full product.
