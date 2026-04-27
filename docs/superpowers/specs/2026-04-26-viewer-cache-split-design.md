# Viewer Cache Split: Processed-Tile Cache + Render Cache

## Purpose

Eliminate the auto-contrast oscillation observed during v1 testing on the
10x mouse-brain dataset. Symptom: image starts color-tinted (one channel
dominant), settles to correct white-balance, then re-tints "out of nowhere"
on a ~500 ms cycle. Sometimes red-tinted, sometimes green-tinted; brightness
also visibly oscillates.

The bug is architectural, not parametric. The viewer's single
`_display_cache` stores the **already-composited RGB output** (clims baked
in). Any clim change forces a full cache clear, which forces async tile
re-loading; while channels arrive at staggered rates the user sees transient
single-channel-tinted composite frames. Combined with `_recompute_auto_contrast`
firing on every paint (including paints triggered by async tile arrivals),
the result is a self-sustaining feedback loop.

This spec splits the cache into two layers — a per-channel processed-tile
cache and a composited-render cache — so clim changes invalidate only the
render layer and re-composite synchronously from hot CPU buffers. The
auto-contrast trigger is also moved off `_on_draw` onto user-driven viewport
events to break the feedback loop.

**Audience:** Anyone touching `squid_tools/viewer/viewport_engine.py`,
`squid_tools/viewer/widget.py`, or the auto-contrast pipeline.

**Guiding principle:** Raw data, processed data, and rendered output are
three distinct lifecycle stages. Caching the wrong one conflates lifecycles
and causes the bug above. Keep them separate.

---

## Current state

`squid_tools/viewer/viewport_engine.py`:
- Single `self._display_cache: dict[str, np.ndarray]` at line 56.
- `get_composite_tiles` (lines 340–428) loads each active channel via
  `_get_pyramid`, runs `self._pipeline` on each (level 0 only), then
  calls `composite_channels(frames, clims, colors)` and stores the
  composited RGB by `display_key = f"disp_{fov_index}_{screen_key}"`.
- `screen_key` includes `target_tile_px`, sorted `active_channels`,
  `z`, `timepoint`, `level` — **but not the clim signature.**
- Cache is `clear()`-ed at lines 89, 123, 135, 140 (load, pipeline change,
  region change, etc.) and from outside in `widget.py`.

`squid_tools/viewer/widget.py`:
- `_autocontrast_timer` (500 ms single-shot) is started in `_on_draw`
  (line 395), which fires on every vispy paint — including async-tile
  arrival paints. This restarts the timer continuously while tiles
  stream in; it fires after 500 ms of paint-quiet.
- `_recompute_auto_contrast` (lines 331–356) iterates active channels,
  calls `engine.compute_contrast`, applies clims, then calls
  `self._engine._display_cache.clear()` and `self._refresh()`.
- The `clear()` is what triggers the visible re-load race.
- `_on_contrast_changed`, `_on_channel_toggled`, `_reset_channel_contrast`
  also call `self._engine._display_cache.clear()`.

## What we're changing

### Cache layers

Replace `self._display_cache` with two caches in `ViewportEngine`:

```python
# Per-channel pipeline output, float32. Survives clim changes.
self._processed_tile_cache: dict[str, np.ndarray] = {}

# Final composited RGB. Invalidated by clim, channel set, level changes.
self._render_cache: dict[str, np.ndarray] = {}
```

**`_processed_tile_cache` key:**
`f"proc_{fov_index}_{channel}_{z}_{timepoint}_L{level}_{target_tile_px}"`

Holds the per-channel float32 array after pyramid loading + pipeline
(`flatfield`, etc.) + screen-resolution downsampling. **Does not** include
clim or color. Survives clim changes. Survives channel-toggle changes.
Cleared only on: dataset load, region change, pipeline change.

**`_render_cache` key:**
`f"rend_{fov_index}_{active_channels_sig}_{clim_sig}_{z}_{timepoint}_L{level}_{target_tile_px}"`

Where:
- `active_channels_sig` = `"_".join(str(c) for c in sorted(active_channels))`
- `clim_sig` = `"_".join(f"{int(round(lo))}:{int(round(hi))}" for ch in sorted(active_channels) for lo, hi in [channel_clims.get(ch, (0.0, 65535.0))])`

Holds composited RGB. Misses naturally on any clim change (because the key
changes), so no explicit invalidation is needed for clim updates. Cleared
on the same events as the processed cache.

### `get_composite_tiles` rewrite

Inner loop becomes:

1. Compute `screen_key` and `clim_sig` for the call.
2. For each visible FOV:
   a. Try `self._render_cache[render_key]` — hit ⇒ append, continue.
   b. For each active channel:
      - Try `self._processed_tile_cache[proc_key]` — hit ⇒ reuse.
      - Miss ⇒ `_get_pyramid` + pipeline (level 0 only) + screen-resolution
        downsample, then store in `_processed_tile_cache`.
   c. Composite via `composite_channels(frames, clims, colors)`, store in
      `_render_cache`.
   d. Append.

Both caches use `MemoryBoundedLRUCache` (the same helper that backs
`self._raw_cache` today). The old `_display_cache` was an unbounded
`dict` — a latent memory leak — so adopting the LRU helper here also
closes that gap. Each cache gets its own byte budget so neither layer
can starve the other:

- `_processed_tile_cache`: budget = `cache_bytes // 2` of the engine's
  `cache_bytes` constructor arg, capped to a sensible upper bound.
- `_render_cache`: same. Composited RGB is denser per tile (3 channels
  uint8 vs N channels float32), so in practice the render cache holds
  more entries per byte.

The exact split is a tunable constant (default 1:1) defined alongside
the existing `cache_bytes` arg, not hard-coded into call sites.

### Auto-contrast lifecycle

The original design here moved the auto-contrast trigger from `_on_draw`
to user-driven viewport events (mouse release / wheel). Subsequent
testing on the mouse-brain dataset showed that any viewport-driven
re-sampling — pan or zoom — leaks viewport state into clims: zoomed-in
samples a smaller FOV subset and gets a different p99 than zoomed-out,
so the same physical region looks brighter at one zoom level than
another. The user's literal request: "run the auto-adjustment on the
highest resolution level and propagate up to the furthest levels."

**Final lifecycle:**

- **Initial load** (`load_acquisition`): one sampling pass per channel
  over the whole region (capped at `max_samples` via `compute_contrast`).
  Sets the canonical clims.
- **Pan / zoom**: nothing. Clims are stable; the same physical pixels look
  the same at every zoom level. Pyramid downsampling is stride-slicing,
  so pyramid-level pixel values are a subset of raw values and share the
  same distribution — no level-aware clim adjustment needed.
- **Per-channel "auto" button** (`_reset_channel_contrast`): re-samples
  that one channel from the **whole region**, not the visible viewport,
  so the result is zoom-independent.
- **Pipeline change** (`set_pipeline`): does not recompute clims. Initial
  clims still apply; user can hit "auto" if a transform shifted the
  intensity range.

In `widget.py`:

- **Remove** `_autocontrast_timer` entirely.
- **Remove** `_recompute_auto_contrast` method.
- **Remove** `connect_viewport_user_change` wiring (the canvas helper
  stays available as API but is no longer wired by the widget).
- **Remove** `_user_tuned_channels` tracking — it existed only to gate
  auto-recompute, which no longer exists.
- **Drop** all `self._engine._display_cache.clear()` calls. The render
  cache misses naturally on clim/channel/level/z/t key changes.

### Engine API surface

`ViewportEngine` exposes two clear methods replacing the ad-hoc
`_display_cache.clear()` reaches from outside:

```python
def invalidate_render(self) -> None:
    """Drop composited cache; processed tiles survive."""
    self._render_cache.clear()

def invalidate_processed(self) -> None:
    """Drop both processed and render caches; pipeline change."""
    self._processed_tile_cache.clear()
    self._render_cache.clear()
```

`widget.py` uses these at the few legitimate sites (e.g., `set_pipeline`
calls `invalidate_processed`). Generic clim/channel changes call neither —
they just update state and refresh.

## Edge cases

- **Pipeline change** (flatfield toggle, etc.): `set_pipeline` calls
  `invalidate_processed`. Both caches drop. Tiles reload + re-process.
- **Pyramid level change** during pan/zoom: `level` is part of both keys;
  old entries fall out via the LRU cap, no manual clear.
- **Channel toggle**: `active_channels` is part of the render key only;
  processed-tile entries for the now-hidden channel stay hot for free
  re-enable. (LRU will evict if cold long enough.)
- **Empty `active_channels`**: existing early-return `[]` in
  `get_composite_tiles` unchanged.
- **Async tile loader interaction**: the loader populates a separate raw-frame
  cache upstream of `_processed_tile_cache`. No race — `get_composite_tiles`
  is called from the main thread and the inner ops are sync. The processed
  cache fills as visible FOVs complete, and the render cache fills
  per-composite. No transient single-channel composites.
- **Clim signature collisions**: integer rounding on clims is fine because
  the slider step (~0.01% of data range) is well below the visible
  perceptual difference. Two slider settings that round to the same int
  pair render identically; that's a feature, not a bug.

## Testing

Unit tests added to `tests/unit/test_viewport_engine_cache.py`:

- **`test_render_cache_hits_on_clim_change`**: load fixture, render once,
  change clims via `compute_contrast` (or direct dict mutation), render
  again. Assert: `_processed_tile_cache` size unchanged, `_load_raw` not
  called between the two renders, `_render_cache` size doubled (one entry
  per (clim_sig) per fov).
- **`test_processed_cache_invalidates_on_pipeline_change`**: render, then
  `engine.set_pipeline([new_transform])`, then render. Assert: both caches
  empty after `set_pipeline`; `_load_raw` called once per active channel
  per visible fov on the second render.
- **`test_channel_toggle_keeps_processed_tiles`**: render with channels
  [0,1], toggle channel 1 off, render. Assert: processed-cache entries for
  channel 0 and channel 1 both present; render-cache has new entry for
  the [0]-only signature; no `_load_raw` for either channel on second
  render.

Manual GUI verification on the 10x mouse brain dataset:
- Launch with `pythonw -m squid_tools ~/Downloads/10x_mouse_brain_2025-04-23_00-53-11.236590`.
- Wait for initial load; the image must stay stable for at least 30 s
  with no panning (no red↔green oscillation, no brightness pulsing).
- Zoom in and out across multiple pyramid levels; the same physical
  region must look the same at every zoom level (no zoom-dependent
  brightness shift).
- Pan to a different stage region; clims must NOT change automatically
  (deliberate — user clicks a channel's "auto" button if they want a
  fresh sample).
- Click a channel's "auto" button at zoomed-in vs zoomed-out positions;
  result must be identical (sampling is whole-region, not viewport).
- Toggle a channel off and on; toggle is instant (processed cache hit,
  no reload).

## Forward references

This refactor explicitly stays CPU-side. The GPU clim path — uniforms +
shader compositor — is captured as v2 cycle **CD1** in
`docs/superpowers/specs/2026-04-21-v2-design.md`. When v2 lands CD1, both
caches in this spec become redundant: the GPU holds raw-channel textures
and computes everything per fragment. The split here is the architectural
prerequisite that makes that future migration straightforward (the CPU
processed cache maps cleanly onto a GPU raw-texture cache).

## Out of scope

- Any change to the async tile loader.
- Any change to `composite_channels` or per-channel colormap math.
- Any change to vispy shaders or canvas rendering primitives.
- Any change to the auto-contrast sampling algorithm itself
  (`compute_contrast` stays as-is; only its trigger moves).
