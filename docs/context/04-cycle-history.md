# Cycle History

Chronological walk through each major cycle merged to master. Each
cycle's spec + plan live in `references/specs/` and `references/plans/`.

---

## Pre-cycle: Initial architecture

Before the named cycles, the project shipped the core connector from
`docs/superpowers/specs/2026-04-09-squid-tools-v1-design.md`:
namespace packages, continuous-zoom viewer, plugin ABC, format
readers, LRU cache + handle pool, AppController, basic GUI shell,
PyInstaller spec, ruff/mypy. This is the foundation all cycles build on.

---

## Cycle A — Selection model + live processing

**Spec:** `references/specs/2026-04-16-selection-live-processing-design.md`
**Plan:** `references/plans/2026-04-16-selection-live-processing.md`

Replaced the toggle-only model with shift+drag selection + Run
button. Added `SelectionState` QObject, canvas rubber-band overlay,
`AlgorithmRunner` QThread, extended plugin ABC with `run_live(selection,
engine, params, progress)`, retrofit flatfield with calibrate-then-
apply, retrofit stitcher with progressive pairwise.

Landed earlier in project history, before this conversation.

---

## Cycle B — Production Logger

**Spec:** `references/specs/2026-04-16-production-logger-design.md`
**Plan:** `references/plans/2026-04-16-production-logger.md`

Replaced ad-hoc `log_panel.log()` calls with Python's `logging`
module. `setup_logging()` installs `RotatingFileHandler` (10MB × 5)
at `~/.squid-tools/logs/`. `LogPanel` attaches a `QtLogHandler` that
marshals records via a Qt signal. Level-filter dropdown (DEBUG / INFO
/ WARN / ERROR, default INFO). Module loggers in controller, runner,
viewport_engine, flatfield, stitching plugins. Legacy `log_panel.log`
preserved via a backwards-compat pass-through.

Commits: 10, spanning setup_logging → short_tag → QtLogHandler →
LogPanel refactor → `__main__.py` wiring → module migrations →
integration test.

---

## Cycle C — Async tile loading (two passes)

**Spec:** `references/specs/2026-04-19-async-tile-loading-design.md`
**Plan:** `references/plans/2026-04-19-async-tile-loading.md`

**First pass** (`feat(tile_loader): Cycle C partial`): `AsyncTileLoader`
with worker QThread, replace-semantics (latest request wins at both
the worker and GUI layers). Seven passing unit tests.

First wiring attempt into `ViewerWidget` crashed tests with SIGABRT —
qtbot uses weakref, ViewerWidget got GC'd before `closeEvent` fired,
QThread destroyed while running → abort. Reverted the widget
integration; tile_loader module stayed.

**Second pass** (`feat(viewer): complete Cycle C`): added
`AsyncTileLoader._async_default` class-level flag + per-test sync
mode fixture (`tests/conftest.py`). Tests run synchronously;
production runs async. Wired into `ViewerWidget._refresh` →
`request()`; `_on_tiles_ready` filters stale replies via
`_last_applied_id`; `closeEvent` stops the loader. Weak registry
+ `stop_all_loaders()` helper for teardown.

---

## Cycle D — Multi-scale pyramid zoom

**Spec:** `references/specs/2026-04-19-multiscale-pyramid-design.md`
**Plan:** `references/plans/2026-04-20-multiscale-pyramid.md`

`viewer/pyramid.py` with `downsample_frame(frame, level)` using
stride-slicing (`frame[::2**L, ::2**L].copy()`). `MAX_PYRAMID_LEVEL=5`.
`ViewportEngine._pyramid_cache` keyed `(fov, z, c, t, level)`.
`_pick_level` heuristic: ratio of viewport/screen mm-per-pixel vs
native, mapped via `bit_length() - 1`. Caps at MAX.
`get_composite_tiles` accepts `level_override` kwarg.

18 new tests, 4 tasks. Pure numpy, no GUI threading changes.

---

## Cycle E — 3D volume rendering primitives

**Spec:** `references/specs/2026-04-20-3d-volume-design.md`

Data path: `ViewportEngine.get_volume(fov, channel, t, level)` stacks
z-planes via `_get_pyramid`. `ViewportEngine.voxel_size_um()` returns
(vx, vy, vz) in micrometers. `compositor.composite_volume_channels`
produces (Z, Y, X, 4) RGBA with alpha = per-voxel max across
channels. `viewer/volume_canvas.py` wraps vispy's `Volume` visual +
`TurntableCamera`; supports both scalar (single-channel with cmap)
and layered multi-channel modes. `scripts/view_volume.py` as
standalone launcher.

11 new tests. Qt widget integration deferred to Cycle O (landed later).

---

## Cycle F — GPU compositing

**Spec:** `references/specs/2026-04-20-gpu-compositing-design.md`

`viewer/compositor.py` with Backend enum (NUMPY / CUPY), auto-
selected at import time via a 2×2 CuPy smoke test. `composite_channels(
frames, clims, colors_rgb, backend=None)` API. CuPy runtime failures
fall back to numpy with a single WARNING log (deduplicated via
`_warned_cupy_failure`). `ViewportEngine.get_composite_tiles` routes
through the new compositor; `get_channel_rgb` resolves per-channel
color. Old `colormaps.composite_channels` removed.

Semantic change: new compositor sums and clips; old one pre-scaled
by `1/n_channels`. Documented at the call site.

17 new tests.

---

## Cycle G — R2 hosting

**Spec:** `references/specs/2026-04-20-r2-hosting-design.md`

`remote/r2_client.py` — `R2Client` wraps boto3 S3 client with
Cloudflare's endpoint. Methods: `upload_file`, `upload_dir`,
`list_keys`, `download_file`, `key_exists`, `presigned_get_url`.
`R2Client.from_env()` reads `CF_R2_ACCOUNT_ID`, `CF_R2_ACCESS_KEY_ID`,
`CF_R2_SECRET_ACCESS_KEY`, `CF_R2_BUCKET`. `scripts/upload_acquisition_
to_r2.py` CLI.

16 unit tests with mocked boto3. No browser viewer yet — Cycle P.

---

## Cycle H — Viewer polish

Addressed macOS testing feedback:
- FOV borders off by default everywhere.
- Per-channel intensity min/max range sliders replacing the plain
  checkbox row (later reduced to single slider — see feedback log).
- Z/T nav row with current-value readouts.
- Copy: "Apply {algo} to viewer" vs "Enable {algo} in pipeline".
- Z/T scrolling preserves user clims (no more auto-contrast jumping).
- Per-channel contrast pre-populated for ALL channels on load.

No dedicated spec; changes follow from user feedback. 367 passing
after this cycle.

---

## Cycle I — Stitcher correctness

Unified the two registration paths. Pre-cycle, the stitcher toggle
called `engine.register_visible_tiles` (different pair-finding) while
the Run button used `plugin.run_live`. The toggle's path reported
"no pairs found" on real acquisitions. Fix: removed `_run_registration`
from app.py; toggle now dispatches via `AlgorithmRunner.run` same as
the Run button. Single pair-finding code path now.

No new spec; one-commit fix.

---

## Cycle J — Absorber v2 (GUI manifest)

Extended the Algorithm Absorber skill with Step 4.5: capture the
source GUI's parameter defaults + exposure as `gui_manifest.yaml`
alongside `plugin.py`.

New module `core/gui_manifest.py` with Pydantic `GuiManifest` model:
- `name`, `source_repo`, `source_gui`, `notes`
- `parameters: dict[str, GuiParameter]` with per-field `default`,
  `visible`, `tooltip`, `min`, `max`, `step`.

`ProcessingTabs._PluginTab.__init__` consults the manifest:
- Hidden params (`visible: false`) collected into `_hidden_defaults`
- Visible params get spinbox widgets with manifest-driven constraints
- `manifest.notes` rendered as a small subtitle under the form

Absorber skill's Step 4.5 documents how to write the manifest.
Skill at `.claude/skills/cephla-algorithm-absorber.md`.

---

## Cycles K, L, M, N — Algorithm absorptions

Four absorptions using Absorber v2:

**K — Deconvolution** (`processing/decon/`). Richardson-Lucy via
scikit-image with a Gaussian PSF derived from objective NA + channel
wavelength + pixel size. 2D per-tile. Full 3D OMW deferred to v2
when CuPy + psfmodels are bundled.

**L — Phase from Defocus** (`processing/phase/`). Parameter surface
mirroring `PhaseReconstructor.__init__` from
`_audit/phase_from_defocus`. `process()` is a v1 stub (passthrough
with a single WARNING log); real reconstruction lands in v2.
Scientific constants captured in manifest (`illumination_na_ratio=
0.87`, wavelength 0.520 µm).

**M — aCNS** (`processing/acns/`). Analytical denoiser: scalar bias
subtraction + sigma thresholding. v1 uses scalar params; v2 will
swap in per-pixel calibration maps from a dark-frame stack.

**N — sep.Background** (`processing/bgsub/`). Per-tile background
estimate + subtraction via sep.Background. Defaults from SExtractor
(bw=bh=64, fw=fh=3).

Each plugin ships with `gui_manifest.yaml`, is registered in
`MainWindow._register_default_plugins` and as a pyproject entry
point.

---

## Cycle O — 3D widget integration

`viewer/widget_3d.py` — `Viewer3DWidget` wraps `Volume3DCanvas` in a
standalone Qt window with FOV spinner, channel checkboxes, Load
button, Close. Single-channel mode uses a cmap; multi-channel
layers one vispy `Volume` per channel (translucent additive).
Opens from the 2D viewer's right-click menu ("Open 3D View…").

2 unit tests, headless-safe (vispy's null backend when no
QApplication).

---

## Cycle P — Browser viewer

`webdemo/viewer.html` — self-contained Canvas2D viewer. Reads
`./tiles.json` (or `?manifest=URL`), pans with drag, zooms with
wheel. Cephla-palette styled header.

`scripts/build_browser_bundle.py` — walks an acquisition, writes
one auto-contrasted PNG per FOV, builds a `tiles.json` manifest of
physical-mm positions, and copies `viewer.html` into an output
folder. Usable locally or uploaded to R2 / Cloudflare Pages.

1 integration test exercising the builder end-to-end.

---

## Convergence push (post-Cycle-P)

After the initial `v1.0.0` tag, multiple user-feedback rounds
drove additional fixes:

- Flatfield × pyramid crash (shape mismatch at level > 0) →
  pipeline transforms skipped at level > 0.
- Stitcher defaults ported from `tilefusion/core.py`; pixel_size_um
  required.
- Decon params require NA + pixel_size from metadata.
- `Acquisition.model_post_init` cross-populates optical from
  objective.
- OME sidecar `ProcessingRun` appended on every run_complete /
  run_failed.
- pyproject.toml split into core + optional extras.
- Dead-code audit noted, cleanup deferred.
- GUI layout reworked: processing tabs → left column, vertical
  tabs, collapsible splitter; SquareContainer keeps canvas 1:1 +
  centered.
- Per-channel sliders collapsed from two (min+max) to one (max,
  with min pinned to auto p1).
- Auto-contrast uses real sampled max instead of 2×p99 heuristic;
  follows viewport on pan via `_autocontrast_timer`.
- No-channels-active crash (`"at least one channel required"`)
  fixed in `get_composite_tiles`.

`v1.0.0` tag was moved forward to include these convergence fixes.

---

## Cycle numbering rules going forward

Cycles continue alphabetically:
- Next v2 cycles likely start at `Q` or go back to thematic
  grouping (e.g. `v2-A1`, `v2-A2` for the distribution P0 items).
- Existing user convention: cycles are alphabetical when the theme
  is clear; versioned when tied to a v-bump item.
