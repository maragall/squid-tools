# Recurring Bugs + Root Causes

Patterns that bit us more than once. Future AI should watch for
these shapes.

---

## 1. Qt thread teardown SIGABRT

**Symptom:** `Fatal Python error: Aborted` with `QThread: Destroyed
while thread 'tile-loader' is still running` in stderr. Often during
pytest, occasionally on app quit.

**Root cause:** `qtbot.addWidget` in pytest-qt keeps widgets via
weakref. When a test function returns, Python GC collects the
widget before its `closeEvent` can fire. A `QThread` owned by the
widget is destroyed while still running; Qt's C++ destructor
aborts.

**Fix pattern:** Any QThread-owning widget needs:
1. A synchronous fallback mode (see `AsyncTileLoader._async_default`
   class-level flag).
2. A conftest fixture that flips the flag to False for tests.
3. An `aboutToQuit` hook or a weak registry + `stop_all_*` helper
   for app-exit cleanup.
4. `closeEvent` that quits + waits the thread with a timeout.

**Found in:**
- `viewer/tile_loader.py` — `AsyncTileLoader`, `stop_all_loaders()`
- `tests/conftest.py` — `_sync_tile_loader` autouse fixture

**Don't-repeat:** When adding a new QThread worker, default its
async mode to False in tests BEFORE wiring it into a widget. Add
the `stop_all_*` module-level helper at the same time.

---

## 2. Pyramid × pipeline shape mismatch

**Symptom:** `ValueError: operands could not be broadcast together
with shapes (521,521) (2084,2084)` spamming the log on every tile
request.

**Root cause:** `ViewportEngine._get_pyramid(fov, z, c, t, level)`
returns a downsampled frame (level > 0 → smaller). Pipeline
transforms (e.g. flatfield) were computed against the full-res
map. Pipeline was then applied to the downsampled frame → shape
mismatch → worker thread exception → log spam + frozen canvas.

**Fix:** Skip pipeline transforms at pyramid level > 0 in
`get_composite_tiles`. Zoomed-out thumbnails are raw; corrections
appear when user zooms to level 0.

**Proper v2 fix:** Downsample correction maps per pyramid level
alongside the frames. Cache per (plugin, level).

**Found in:** `viewer/viewport_engine.py:get_composite_tiles`

---

## 3. Composite crash on empty active_channels

**Symptom:** `ValueError: at least one channel required` spamming
the log when user toggles off every channel.

**Root cause:** `widget.py:_on_channel_toggled` sets
`active_channels = []` when all checkboxes are unchecked. Then
`get_composite_tiles` iterates zero channels, passes `frames=[]`
to the compositor, which raises.

**Fix:** Early-return empty tile list in `get_composite_tiles`
when `active_channels` is empty. No crash, just a black canvas.

**Don't-repeat:** Any engine method that takes a list should
handle empty as a legitimate state — don't delegate the empty
check to a downstream validator.

**Found in:** `viewer/viewport_engine.py:get_composite_tiles`

---

## 4. Hardcoded metadata fallbacks

**Symptom:** Plugin uses a Cephla-10x-ish default when the user's
acquisition is a different objective. Output numerically correct
for the default pixel size but wrong for the actual data.

**Root cause:** `default_params(optical)` had silent fallbacks like
`pixel_size_um or 0.325`. When metadata is missing (or reader fails
to populate), the plugin silently uses a fiction.

**Fix:** Plugins that depend on acquisition-specific values MUST
raise `ValueError` with a clear message if metadata is missing. No
silent fallbacks.

**Found in:**
- `processing/stitching/plugin.py:default_params`
- `processing/decon/plugin.py:default_params`

**Upstream fix:** `Acquisition.model_post_init` cross-populates
`.optical` from `.objective` so readers only need to fill the
authoritative field once.

**Don't-repeat:** Grep for `or 0\.` and `or 1\.` in plugin code.
Any such fallback is a bug waiting.

---

## 5. Stale display cache after mutation

**Symptom:** Channel toggle or position override happens, but
canvas shows the old composite.

**Root cause:** `_display_cache` keyed on `(fov, level, channels,
z, t)`. Position overrides and channel toggles don't change the
key, so cached pre-composited RGB tiles are served stale.

**Fix:** Every mutation that invalidates the composite must
explicitly `.clear()` the display cache:
- `set_position_overrides` → clears
- `clear_position_overrides` → clears
- `_on_channel_toggled` → clears
- `_on_contrast_changed` → clears
- `_on_slider_changed` (Z/T) → clears

**Don't-repeat:** When adding a new state mutation method to the
engine, add the `_display_cache.clear()` call. Better: include the
state in the cache key so the cache auto-invalidates.

**Found in:** `viewer/viewport_engine.py` (multiple sites)

---

## 6. Forgetting `self.` or `Qt` property / method distinction

**Symptom:** `TypeError: 'float' object is not callable` after I
wrote `self.pixel_size_um()` when it's a `@property`.

**Root cause:** `ViewportEngine.pixel_size_um` is a `@property`
(line 112 of viewport_engine.py). I called it as a method in a
new path. Python didn't complain until runtime.

**Fix:** Know which names are properties. Our conventions:
- `pixel_size_um`, `tile_size_mm` → `@property` (no parens)
- `compute_contrast`, `get_composite_tiles`, `bounding_box` → methods

**Don't-repeat:** When editing engine call sites, grep for
`@property` first. mypy would catch this if we ran it in strict
mode across all files — v2 item.

---

## 7. Reinvention drift

**Symptom:** The AI writes code that solves a problem differently
from the reference repo, then the user tests and the output looks
wrong.

**Examples across the session:**
- CPU compositor vs napari's GPU layer mode (ref:
  `_audit/ndviewer_light/.../core.py:1544`)
- Stitcher defaults ported incorrectly (ref:
  `_audit/stitcher/src/tilefusion/core.py:85-115`)
- Channel color ramp — flat `normalized * RGB` vs napari's colormap
  luminance ramp (ref: `_audit/image-stitcher/.../grid_viewer_gui.
  py:1167`)

**Root cause:** Writing before reading. Default should be to check
`_audit/` first.

**Fix pattern:** Before implementing anything related to viewer,
contrast, compositing, stitching, flatfield, phase, or decon, grep
the corresponding `_audit/` directory for the concept. Prefer to
port an existing function; only reinvent if the reference is
architecturally incompatible.

---

## 8. Layout constraints applied to the wrong widget

**Symptom:** Canvas still looks rectangular after adding a
"SquareContainer". User says "HAHAHA look at aspect ratios."

**Root cause:** SquareContainer wrapped the entire `ViewerWidget`
(which includes the canvas + sliders + nav). The square
constraint applied to the whole widget, but the canvas was a
child that still laid out based on its own layout manager.

**Fix:** Move the constraint ONE LEVEL DEEPER. SquareContainer now
wraps the vispy native widget directly inside ViewerWidget.
Sliders + nav strip live BELOW the square.

**Don't-repeat:** When constraining geometry, be explicit about
which widget receives the constraint. The layout structure matters
more than the constraint.

---

## 9. Pydantic field default that should be a hook-time derivation

**Symptom:** Plugin's Pydantic model has `default=525.0` for
wavelength. Gets 525 even when acquisition's channel metadata has
a different wavelength.

**Root cause:** Pydantic `Field(default=...)` is evaluated at
instance creation, not from context. `default_params(optical)` is
the right place to derive defaults from metadata.

**Fix:** Remove field defaults for acquisition-derived values.
Make them required. `default_params` populates them from the
acquisition. If acquisition lacks them, raise.

**Don't-repeat:** In a plugin's Pydantic model, ask: "does this
default depend on the acquisition?" If yes, no `default=`.

---

## 10. pytest flakiness from shared Qt app state

**Symptom:** A test passes alone but fails when run with the rest
of the suite. Or: whole suite passes but a single test's standalone
run fails.

**Root cause:** pytest-qt shares the `QApplication` across tests.
Widgets from one test can leak signals or global state into
another. QThreads that haven't been stopped persist.

**Fix pattern:**
- Autouse fixtures that reset global state (logging handlers,
  async loader flags).
- Every test that creates a widget must either let qtbot manage it
  (`qtbot.addWidget`) OR explicitly `widget.close()` at end.
- Avoid module-level singletons. Use pytest fixtures with `function`
  scope.

**Found in:**
- `tests/conftest.py` — global fixtures.
- `tests/integration/conftest.py` — `_detach_qt_log_handlers`.
