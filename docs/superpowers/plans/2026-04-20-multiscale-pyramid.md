# Multi-scale Pyramid Zoom Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add pyramid-level-aware tile fetching to `ViewportEngine`. Users panning/zooming over large mosaics get instant feedback because the engine streams downsampled tiles at zoom-out and full-res tiles only when zoomed in close.

**Architecture:** New module `squid_tools/viewer/pyramid.py` with a pure-numpy `downsample_frame` (stride-slicing, 2x per level, cap at 5). `ViewportEngine` gains `_pyramid_cache`, `_pick_level`, `_get_pyramid`, and `get_composite_tiles` accepts an optional `level_override`. No GUI threading changes; level selection is a synchronous computation on the main thread.

**Tech Stack:** numpy (stride slicing), existing `ViewportEngine`, pytest.

**Spec:** `docs/superpowers/specs/2026-04-19-multiscale-pyramid-design.md`

---

## File Structure

```
squid_tools/viewer/
├── pyramid.py                  # NEW: downsample_frame + MAX_PYRAMID_LEVEL
├── viewport_engine.py          # MODIFY: _pyramid_cache, _pick_level, _get_pyramid, get_composite_tiles
tests/
├── unit/
│   ├── test_pyramid.py         # NEW
│   └── test_viewport_engine.py # MODIFY (add pyramid tests)
```

---

### Task 1: `pyramid.py` — `downsample_frame` + `MAX_PYRAMID_LEVEL`

**Files:**
- Create: `squid_tools/viewer/pyramid.py`
- Create: `tests/unit/test_pyramid.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_pyramid.py`:
```python
"""Tests for pyramid decimation."""

from __future__ import annotations

import numpy as np
import pytest

from squid_tools.viewer.pyramid import MAX_PYRAMID_LEVEL, downsample_frame


class TestMaxLevel:
    def test_constant_value(self) -> None:
        assert MAX_PYRAMID_LEVEL == 5


class TestDownsampleFrame:
    def test_level_zero_returns_original(self) -> None:
        frame = np.arange(64, dtype=np.float32).reshape(8, 8)
        out = downsample_frame(frame, 0)
        assert out is frame  # identity, no copy

    def test_level_one_halves_both_dims_2d(self) -> None:
        frame = np.arange(64, dtype=np.float32).reshape(8, 8)
        out = downsample_frame(frame, 1)
        assert out.shape == (4, 4)
        # Stride slicing: out[i, j] == frame[2*i, 2*j]
        assert out[0, 0] == frame[0, 0]
        assert out[1, 1] == frame[2, 2]

    def test_level_two_quarters_both_dims_2d(self) -> None:
        frame = np.arange(64, dtype=np.float32).reshape(8, 8)
        out = downsample_frame(frame, 2)
        assert out.shape == (2, 2)
        assert out[0, 0] == frame[0, 0]
        assert out[1, 1] == frame[4, 4]

    def test_3d_frame_preserves_leading_axis(self) -> None:
        frame = np.arange(3 * 8 * 8, dtype=np.float32).reshape(3, 8, 8)
        out = downsample_frame(frame, 1)
        assert out.shape == (3, 4, 4)
        assert out[0, 0, 0] == frame[0, 0, 0]
        assert out[1, 1, 1] == frame[1, 2, 2]

    def test_returns_copy_at_level_one(self) -> None:
        frame = np.arange(16, dtype=np.float32).reshape(4, 4)
        out = downsample_frame(frame, 1)
        out[0, 0] = 999
        assert frame[0, 0] == 0  # original untouched

    def test_negative_level_raises(self) -> None:
        frame = np.zeros((4, 4), dtype=np.float32)
        with pytest.raises(ValueError, match="level must be >= 0"):
            downsample_frame(frame, -1)

    def test_1d_frame_raises(self) -> None:
        frame = np.zeros(4, dtype=np.float32)
        with pytest.raises(ValueError, match="must be 2D or 3D"):
            downsample_frame(frame, 1)

    def test_4d_frame_raises(self) -> None:
        frame = np.zeros((2, 2, 2, 2), dtype=np.float32)
        with pytest.raises(ValueError, match="must be 2D or 3D"):
            downsample_frame(frame, 1)
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/test_pyramid.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'squid_tools.viewer.pyramid'`

- [ ] **Step 3: Minimal implementation**

`squid_tools/viewer/pyramid.py`:
```python
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
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_pyramid.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add squid_tools/viewer/pyramid.py tests/unit/test_pyramid.py
git commit -m "feat(pyramid): downsample_frame via stride slicing, MAX_PYRAMID_LEVEL=5"
```

---

### Task 2: `ViewportEngine._pyramid_cache` + `_get_pyramid`

**Files:**
- Modify: `squid_tools/viewer/viewport_engine.py`
- Modify: `tests/unit/test_viewport_engine.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_viewport_engine.py`:
```python
class TestViewportEnginePyramidCache:
    def test_get_pyramid_level_zero_returns_raw(
        self, individual_acquisition,
    ) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        frame = engine._get_pyramid(fov=0, z=0, channel=0, timepoint=0, level=0)
        assert frame.ndim in (2, 3)
        # Level 0 is NOT cached (returns raw directly)
        assert (0, 0, 0, 0, 0) not in engine._pyramid_cache

    def test_get_pyramid_level_one_caches_and_halves(
        self, individual_acquisition,
    ) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        raw = engine._load_raw(fov=0, z=0, channel=0, timepoint=0)
        level1 = engine._get_pyramid(fov=0, z=0, channel=0, timepoint=0, level=1)
        assert level1.shape[-2] == raw.shape[-2] // 2
        assert level1.shape[-1] == raw.shape[-1] // 2
        # Cached
        assert (0, 0, 0, 0, 1) in engine._pyramid_cache

    def test_get_pyramid_cache_hit_returns_same_array(
        self, individual_acquisition,
    ) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        first = engine._get_pyramid(fov=0, z=0, channel=0, timepoint=0, level=2)
        second = engine._get_pyramid(fov=0, z=0, channel=0, timepoint=0, level=2)
        assert first is second  # cache returns identical object
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/unit/test_viewport_engine.py::TestViewportEnginePyramidCache -v`
Expected: FAIL — `AttributeError: 'ViewportEngine' object has no attribute '_pyramid_cache'` (or `_get_pyramid`).

- [ ] **Step 3: Implement in `ViewportEngine`**

In `squid_tools/viewer/viewport_engine.py`:

a) Inside `ViewportEngine.__init__`, add alongside other cache initializations:
```python
        self._pyramid_cache: dict[
            tuple[int, int, int, int, int], np.ndarray,
        ] = {}
```

b) Inside `ViewportEngine.load`, after the engine state is rebuilt (near the existing cache clears), add:
```python
        self._pyramid_cache.clear()
```

c) Add the method (near `_load_raw`, in the private section):
```python
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
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_viewport_engine.py -v`
Expected: PASS (all existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add squid_tools/viewer/viewport_engine.py tests/unit/test_viewport_engine.py
git commit -m "feat(viewport_engine): _get_pyramid + _pyramid_cache (level>=1 cached)"
```

---

### Task 3: `ViewportEngine._pick_level`

**Files:**
- Modify: `squid_tools/viewer/viewport_engine.py`
- Modify: `tests/unit/test_viewport_engine.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_viewport_engine.py`:
```python
class TestViewportEnginePickLevel:
    def test_level_zero_when_zoomed_in(self, individual_acquisition) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        # Tiny viewport, big screen → zoomed in, native resolution
        level = engine._pick_level(
            viewport=(0.0, 0.0, 0.1, 0.1),
            screen_width=10000, screen_height=10000,
        )
        assert level == 0

    def test_higher_level_when_zoomed_out(self, individual_acquisition) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        # Big viewport, small screen → zoomed way out, high level
        level = engine._pick_level(
            viewport=(0.0, 0.0, 100.0, 100.0),
            screen_width=100, screen_height=100,
        )
        assert level >= 1

    def test_level_capped_at_max(self, individual_acquisition) -> None:
        from squid_tools.viewer.pyramid import MAX_PYRAMID_LEVEL
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        # Enormous viewport, tiny screen → would otherwise exceed max
        level = engine._pick_level(
            viewport=(0.0, 0.0, 100000.0, 100000.0),
            screen_width=1, screen_height=1,
        )
        assert level == MAX_PYRAMID_LEVEL

    def test_zero_screen_size_returns_level_zero(
        self, individual_acquisition,
    ) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        assert engine._pick_level(
            viewport=(0.0, 0.0, 1.0, 1.0), screen_width=0, screen_height=0,
        ) == 0
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/unit/test_viewport_engine.py::TestViewportEnginePickLevel -v`
Expected: FAIL — `AttributeError: 'ViewportEngine' object has no attribute '_pick_level'`

- [ ] **Step 3: Implement `_pick_level`**

Add to `ViewportEngine`:
```python
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
        native_mm_per_px = self.pixel_size_um() / 1000.0
        if native_mm_per_px <= 0 or mm_per_px <= 0:
            return 0
        ratio = int(mm_per_px / native_mm_per_px)
        if ratio < 2:
            return 0
        level = ratio.bit_length() - 1
        return min(level, MAX_PYRAMID_LEVEL)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_viewport_engine.py -v`
Expected: PASS (all existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add squid_tools/viewer/viewport_engine.py tests/unit/test_viewport_engine.py
git commit -m "feat(viewport_engine): _pick_level from viewport/screen ratio"
```

---

### Task 4: `get_composite_tiles` uses pyramid + integration test

**Files:**
- Modify: `squid_tools/viewer/viewport_engine.py`
- Modify: `tests/unit/test_viewport_engine.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_viewport_engine.py`:
```python
class TestViewportEngineCompositeWithPyramid:
    def test_level_override_passes_through(self, individual_acquisition) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        bb = engine.bounding_box()
        tiles_level0 = engine.get_composite_tiles(
            viewport=bb, screen_width=800, screen_height=600,
            active_channels=[0], channel_names=["C1"],
            channel_clims={0: (0.0, 1.0)},
            z=0, timepoint=0,
            level_override=0,
        )
        tiles_level2 = engine.get_composite_tiles(
            viewport=bb, screen_width=800, screen_height=600,
            active_channels=[0], channel_names=["C1"],
            channel_clims={0: (0.0, 1.0)},
            z=0, timepoint=0,
            level_override=2,
        )
        # Same number of tiles; each level-2 image is 1/4 in each dim
        assert len(tiles_level0) == len(tiles_level2)
        # Grab first tile's frame shape at each level
        # Tile shape depends on ViewportEngine's tile format; check pyramid cache populated
        assert any(k[4] == 2 for k in engine._pyramid_cache)

    def test_auto_level_selects_when_override_none(
        self, individual_acquisition,
    ) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        bb = engine.bounding_box()
        # Very zoomed out (small screen, big bounding box if acq is tiny,
        # but pad the viewport to guarantee ratio > 2)
        huge_vp = (bb[0] - 100.0, bb[1] - 100.0, bb[2] + 100.0, bb[3] + 100.0)
        engine.get_composite_tiles(
            viewport=huge_vp, screen_width=50, screen_height=50,
            active_channels=[0], channel_names=["C1"],
            channel_clims={0: (0.0, 1.0)},
            z=0, timepoint=0,
        )
        # At least one level >=1 entry should be in the cache
        assert any(k[4] >= 1 for k in engine._pyramid_cache)
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/unit/test_viewport_engine.py::TestViewportEngineCompositeWithPyramid -v`
Expected: FAIL — `get_composite_tiles` doesn't accept `level_override`, or doesn't populate `_pyramid_cache`.

- [ ] **Step 3: Modify `get_composite_tiles`**

Read the current signature. Add `level_override: int | None = None` as a keyword-only argument (put it after existing kwargs).

Inside the function body, replace the line(s) that load each frame (currently via `self._load_raw(...)` inside the compositing loop) with:

```python
        level = (
            level_override
            if level_override is not None
            else self._pick_level(viewport, screen_width, screen_height)
        )
        # ... inside the loop over visible FOVs / channels:
        #     frame = self._get_pyramid(fov, z, channel, timepoint, level)
```

Be careful: the current `get_composite_tiles` calls into `_load_raw` indirectly — you may need to trace where raw frames are loaded and replace those calls with `self._get_pyramid(fov, z, channel, timepoint, level)`. Read the method carefully before editing.

If `get_composite_tiles` delegates to a helper that loads frames, modify the helper to accept `level` and call `_get_pyramid` at that level.

**Keep the output tile metadata (x_mm, y_mm, width_mm, height_mm) unchanged** — those describe physical space, not pixel count. The tile's frame array is the only thing that changes size.

- [ ] **Step 4: Run the full test suite**

Run: `pytest -q`
Expected: all passing (289 + 15 new = 304, approximately). Existing `test_viewport_engine.py` tests that call `get_composite_tiles` without `level_override` should still pass because default auto-select falls back to level 0 for small viewports.

- [ ] **Step 5: ruff**

Run: `ruff check squid_tools tests`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add squid_tools/viewer/viewport_engine.py tests/unit/test_viewport_engine.py
git commit -m "feat(viewport_engine): get_composite_tiles honors pyramid level"
```

---

## Self-Review

**Spec coverage:**
- `downsample_frame` 2D + 3D, stride slicing → Task 1 ✓
- `MAX_PYRAMID_LEVEL=5` → Task 1 ✓
- `_pyramid_cache` dict → Task 2 ✓
- Level 0 bypasses cache → Task 2 ✓
- `_get_pyramid` cache semantics → Task 2 ✓
- `_pick_level` heuristic (bit_length approach) → Task 3 ✓
- `_pick_level` caps at MAX_PYRAMID_LEVEL → Task 3 ✓
- `_pick_level` guards against zero screen/pixel-size → Task 3 ✓
- `get_composite_tiles` auto-selects level → Task 4 ✓
- `level_override` parameter → Task 4 ✓
- Cache cleared on acquisition reload → Task 2 ✓

**Placeholder scan:** No TODO / TBD. Each step has runnable code.

**Type consistency:** Cache key `tuple[int, int, int, int, int]` (fov, z, c, t, level) used consistently.

**Scope:** Single subsystem (viewport_engine + new pyramid helper). Pure numpy. No GUI threading. No canvas changes.

**Ambiguity:** Task 4 Step 3 says "trace where raw frames are loaded." This is intentional — the implementer must read `get_composite_tiles` first because I can't predict which helpers it calls in the current implementation. The contract is clear: replace `_load_raw(fov, z, c, t)` with `_get_pyramid(fov, z, c, t, level)` in all tile-loading sites within `get_composite_tiles`.
