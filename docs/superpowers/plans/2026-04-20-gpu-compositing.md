# GPU Compositing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move multi-channel additive compositing into a compositor module with a numpy backend (default) and an optional CuPy backend (auto-selected on GPU-equipped machines). `ViewportEngine.get_composite_tiles` routes through the new compositor. The old `composite_channels` in `colormaps.py` is removed.

**Architecture:** `squid_tools/viewer/compositor.py` owns `composite_channels(frames, clims, colors_rgb, backend=None)`. Backend chosen at import time via a 2x2 CuPy smoke test; CuPy failures at runtime fall back to numpy and log a WARNING once. `ViewportEngine` resolves channel colors via the existing `get_channel_rgb(name)` helper and passes them in explicitly.

**Tech Stack:** numpy (always), CuPy (optional), pytest.

**Spec:** `docs/superpowers/specs/2026-04-20-gpu-compositing-design.md`

---

## File Structure

```
squid_tools/viewer/
├── compositor.py               # NEW: Backend enum, composite_channels, numpy + cupy backends
├── colormaps.py                # MODIFY: remove the old composite_channels function
├── viewport_engine.py          # MODIFY: switch import + call site to new compositor
tests/
├── unit/
│   └── test_compositor.py      # NEW
```

---

### Task 1: `compositor.py` — numpy backend + API

**Files:**
- Create: `squid_tools/viewer/compositor.py`
- Create: `tests/unit/test_compositor.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_compositor.py`:
```python
"""Tests for the multi-channel compositor."""

from __future__ import annotations

import numpy as np
import pytest

from squid_tools.viewer.compositor import (
    Backend,
    DEFAULT_BACKEND,
    composite_channels,
)


class TestBackendEnum:
    def test_enum_values(self) -> None:
        assert Backend.NUMPY.value == "numpy"
        assert Backend.CUPY.value == "cupy"

    def test_default_backend_is_a_backend(self) -> None:
        assert DEFAULT_BACKEND in (Backend.NUMPY, Backend.CUPY)


class TestCompositeValidation:
    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one channel"):
            composite_channels([], [], [])

    def test_length_mismatch_raises(self) -> None:
        frame = np.zeros((4, 4), dtype=np.float32)
        with pytest.raises(ValueError, match="same length"):
            composite_channels(
                [frame, frame], [(0.0, 1.0)], [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            )

    def test_non_2d_frame_raises(self) -> None:
        frame3d = np.zeros((2, 4, 4), dtype=np.float32)
        with pytest.raises(ValueError, match="frames must be 2D"):
            composite_channels([frame3d], [(0.0, 1.0)], [(1.0, 0.0, 0.0)])

    def test_mismatched_frame_shapes_raise(self) -> None:
        a = np.zeros((4, 4), dtype=np.float32)
        b = np.zeros((5, 4), dtype=np.float32)
        with pytest.raises(ValueError, match="same shape"):
            composite_channels(
                [a, b], [(0.0, 1.0), (0.0, 1.0)],
                [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            )


class TestCompositeNumpyBackend:
    def test_single_red_channel_full_bright(self) -> None:
        frame = np.ones((4, 4), dtype=np.float32)
        out = composite_channels(
            [frame], [(0.0, 1.0)], [(1.0, 0.0, 0.0)],
            backend=Backend.NUMPY,
        )
        assert out.shape == (4, 4, 3)
        assert out.dtype == np.float32
        assert np.allclose(out[..., 0], 1.0)
        assert np.allclose(out[..., 1], 0.0)
        assert np.allclose(out[..., 2], 0.0)

    def test_single_red_channel_half_bright(self) -> None:
        frame = np.full((4, 4), 0.5, dtype=np.float32)
        out = composite_channels(
            [frame], [(0.0, 1.0)], [(1.0, 0.0, 0.0)],
            backend=Backend.NUMPY,
        )
        assert np.allclose(out[..., 0], 0.5)
        assert np.allclose(out[..., 1:], 0.0)

    def test_two_channels_red_and_green(self) -> None:
        red_frame = np.ones((4, 4), dtype=np.float32)
        green_frame = np.ones((4, 4), dtype=np.float32)
        out = composite_channels(
            [red_frame, green_frame],
            [(0.0, 1.0), (0.0, 1.0)],
            [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            backend=Backend.NUMPY,
        )
        # Both channels contribute fully → yellow (clipped to 1.0 per channel)
        assert np.allclose(out[..., 0], 1.0)
        assert np.allclose(out[..., 1], 1.0)
        assert np.allclose(out[..., 2], 0.0)

    def test_clim_normalization(self) -> None:
        frame = np.full((4, 4), 1000.0, dtype=np.float32)
        out = composite_channels(
            [frame], [(500.0, 1500.0)], [(1.0, 0.0, 0.0)],
            backend=Backend.NUMPY,
        )
        # (1000 - 500) / (1500 - 500) = 0.5
        assert np.allclose(out[..., 0], 0.5)

    def test_value_below_clim_clips_to_zero(self) -> None:
        frame = np.zeros((2, 2), dtype=np.float32)
        out = composite_channels(
            [frame], [(10.0, 20.0)], [(1.0, 0.0, 0.0)],
            backend=Backend.NUMPY,
        )
        assert np.allclose(out, 0.0)

    def test_value_above_clim_clips_to_color(self) -> None:
        frame = np.full((2, 2), 1000.0, dtype=np.float32)
        out = composite_channels(
            [frame], [(10.0, 20.0)], [(1.0, 0.0, 0.0)],
            backend=Backend.NUMPY,
        )
        assert np.allclose(out[..., 0], 1.0)
        assert np.allclose(out[..., 1:], 0.0)

    def test_zero_width_clim_does_not_divide_by_zero(self) -> None:
        frame = np.full((2, 2), 5.0, dtype=np.float32)
        out = composite_channels(
            [frame], [(5.0, 5.0)], [(1.0, 0.0, 0.0)],
            backend=Backend.NUMPY,
        )
        assert out.shape == (2, 2, 3)
        assert np.all(np.isfinite(out))

    def test_output_float32(self) -> None:
        frame = np.ones((2, 2), dtype=np.uint16) * 100
        out = composite_channels(
            [frame], [(0.0, 200.0)], [(1.0, 0.0, 0.0)],
            backend=Backend.NUMPY,
        )
        assert out.dtype == np.float32


class TestBackendOverride:
    def test_explicit_numpy_backend(self) -> None:
        frame = np.ones((4, 4), dtype=np.float32)
        out = composite_channels(
            [frame], [(0.0, 1.0)], [(1.0, 0.0, 0.0)],
            backend=Backend.NUMPY,
        )
        assert out.shape == (4, 4, 3)
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/unit/test_compositor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'squid_tools.viewer.compositor'`

- [ ] **Step 3: Implement `compositor.py`**

`squid_tools/viewer/compositor.py`:
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
```

- [ ] **Step 4: Run tests + ruff**

Run: `pytest tests/unit/test_compositor.py -v`
Expected: PASS (all).

Run: `ruff check squid_tools/viewer/compositor.py tests/unit/test_compositor.py`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add squid_tools/viewer/compositor.py tests/unit/test_compositor.py
git commit -m "feat(compositor): numpy backend + CuPy fallback, explicit frames/clims/colors API"
```

---

### Task 2: Switch `ViewportEngine` to new compositor; drop old `colormaps.composite_channels`

**Files:**
- Modify: `squid_tools/viewer/viewport_engine.py`
- Modify: `squid_tools/viewer/colormaps.py`
- Modify: `tests/unit/test_viewport_engine.py` (only if affected)

- [ ] **Step 1: Inspect current call site**

Read `squid_tools/viewer/viewport_engine.py:334-410` to see how `composite_channels` is called today. It takes `list[tuple[np.ndarray, str, tuple[float, float]]]` — channel-name-based color lookup happens inside the old function.

Read `squid_tools/viewer/colormaps.py:68-106` to see `composite_channels` and `get_channel_rgb`.

- [ ] **Step 2: Swap the call site**

In `viewport_engine.py`, replace:
```python
from squid_tools.viewer.colormaps import composite_channels
# ...
data = composite_channels(channel_data)
```

with:
```python
from squid_tools.viewer.colormaps import get_channel_rgb
from squid_tools.viewer.compositor import composite_channels
# ...
frames = [cd[0] for cd in channel_data]
colors = [get_channel_rgb(cd[1]) for cd in channel_data]
clims = [cd[2] for cd in channel_data]
data = composite_channels(frames, clims, colors)
```

Preserve whatever `channel_data` structure the engine already builds. Don't restructure unrelated code.

- [ ] **Step 3: Normalize-by-channel-count equivalence**

The **old** compositor divided each channel's contribution by `n_channels` (to prevent blowout). The **new** compositor does NOT — it sums raw contributions and clips at the end. This is a semantic change: bright regions that would have been pre-scaled now clip instead.

Accept the new behavior (the spec calls for simple additive + clip). Add a comment in `viewport_engine.py` right above the `composite_channels` call noting the change, e.g.:
```python
# Note: compositor sums channel contributions and clips at [0, 1].
# Heavy multi-channel regions may saturate; adjust clims to compensate.
```

If any existing tests assert on specific composite pixel values that depended on the old `/n_channels` scaling, update them to match the new semantics. Read `tests/unit/test_viewport_engine.py`, `tests/unit/test_viewer_colormaps.py` carefully to find such assertions — most tests probably check shape/bounds only, not exact values.

- [ ] **Step 4: Remove old `composite_channels` from `colormaps.py`**

Delete the `composite_channels` function (lines 76-106 approximately) and any `import numpy` import no longer needed after the removal.

- [ ] **Step 5: Run full suite**

Run: `pytest -q`
Expected: all passing. If any test fails because of the composition semantics change, update the test to expect the new behavior (not the `/n_channels` scaling).

Run: `ruff check squid_tools tests`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add squid_tools/viewer/viewport_engine.py squid_tools/viewer/colormaps.py tests
git commit -m "feat(viewport_engine): route compositing through compositor; drop colormaps.composite_channels"
```

---

### Task 3: Backend log + integration test

**Files:**
- Modify: `tests/unit/test_compositor.py`

- [ ] **Step 1: Write the test**

Append to `tests/unit/test_compositor.py`:
```python
class TestBackendLogging:
    def test_default_backend_logged_at_import(self, caplog) -> None:
        import importlib
        import logging

        import squid_tools.viewer.compositor as compositor_mod

        caplog.set_level(logging.INFO, logger="squid_tools.viewer.compositor")
        importlib.reload(compositor_mod)
        messages = [
            r.getMessage() for r in caplog.records
            if r.name == "squid_tools.viewer.compositor"
            and r.levelno == logging.INFO
        ]
        assert any("compositor backend:" in m for m in messages)


class TestCompositorIntegrationWithEngine:
    def test_composite_tiles_renders_rgb_via_new_compositor(
        self, individual_acquisition,
    ) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        bb = engine.bounding_box()
        tiles = engine.get_composite_tiles(
            viewport=bb, screen_width=100, screen_height=100,
            active_channels=[0], channel_names=["BF LED matrix full"],
            channel_clims={0: (0.0, 1.0)},
            z=0, timepoint=0,
            level_override=0,
        )
        # At least one tile produced
        assert len(tiles) > 0
        # Each tile's data is (H, W, 3) float32
        first = tiles[0]
        data = first.data if hasattr(first, "data") else first[0]
        assert data.ndim == 3
        assert data.shape[-1] == 3
        assert data.dtype == np.float32
```

Note: `"BF LED matrix full"` may not match the fixture acquisition's channel. If the integration test fails because of channel-name mismatch, inspect `individual_acquisition`'s actual channels and use whichever name it has (fall back to `"C1"`).

- [ ] **Step 2: Run tests**

Run: `pytest tests/unit/test_compositor.py -v`
Expected: PASS (all existing + 2 new).

Run: `pytest -q`
Expected: all passing.

Run: `ruff check squid_tools tests`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_compositor.py
git commit -m "test(compositor): backend log + integration through ViewportEngine"
```

---

## Self-Review

**Spec coverage:**
- `compositor.py` with Backend enum, DEFAULT_BACKEND, composite_channels → Task 1 ✓
- Numpy + CuPy backend implementations → Task 1 ✓
- Backend auto-selection at import (CuPy smoke test) → Task 1 ✓
- CuPy failure fallback with one-time WARNING → Task 1 ✓
- Validation (empty, length mismatch, non-2D, shape mismatch, zero-width clim) → Task 1 ✓
- ViewportEngine uses new compositor → Task 2 ✓
- Old colormaps.composite_channels removed → Task 2 ✓
- Backend logged at module import → Task 3 ✓

**Placeholder scan:** No TODO / TBD. Channel-name fallback noted for the integration test.

**Type consistency:** `composite_channels(frames, clims, colors_rgb, backend=None) -> np.ndarray` used identically across task 1 tests and the engine call site.

**Scope:** One new module (compositor.py), one modified module (viewport_engine.py + colormaps.py cleanup), tests. No GUI threading or widget changes.

**Ambiguity:** The semantic change (drop `/n_channels` scaling) is called out in Task 2 Step 3 with a code comment plan. If tests break because of that, update them to the new semantics.
