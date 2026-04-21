# Squid-Tools

Post-processing companion for Cephla-Lab / Squid microscopy data. A PySide6 + vispy desktop app that reads Squid's acquisition formats, renders a continuous-zoom stage view, and runs processing modules (flatfield, stitching, deconvolution, …) interactively.

**Status:** v1 candidate. See [v1 status](#v1-status) below for what's in the box.

---

## Quick start

```bash
# Launch against a Squid acquisition directory
python -m squid_tools /path/to/acquisition

# Or open via the menu: File > Open Acquisition
python -m squid_tools
```

Other launchers:

```bash
# 3D volume viewer (one FOV at a time, rotatable)
python scripts/view_volume.py /path/to/acquisition --fov 0

# Upload an acquisition to Cloudflare R2 (for web demos)
export CF_R2_ACCOUNT_ID=... CF_R2_ACCESS_KEY_ID=... CF_R2_SECRET_ACCESS_KEY=... CF_R2_BUCKET=...
python scripts/upload_acquisition_to_r2.py --path /path/to/acq --prefix demo/my_acq
```

Dev mode (hot-load a plugin file):

```bash
python -m squid_tools --dev processing/my_new_algo/plugin.py
```

---

## What it does

Squid-tools reads an acquisition directory (OME-TIFF, individual-images, or Zarr), shows you the whole stage at once, and lets you run algorithms on tiles you select. Every algorithm is a plugin that implements one ABC, so adding a new one is a single folder.

| Region | Purpose |
|---|---|
| **Top ribbon** | One tab per installed algorithm plugin. Each tab has parameters + a "Run" button. |
| **Left controls** | FOV borders, layer toggles. |
| **Center viewer** | Continuous-zoom vispy canvas. Pan with mouse, zoom with scroll. Shift+drag selects FOVs. Right-click for Fit/Borders. |
| **Right region selector** | Well-plate grid or region dropdown (auto-detected from `acquisition.yaml`). |
| **Bottom log panel** | Timestamped log console with a level-filter dropdown. Status bar shows cache occupancy, heap, GPU. |

### Interaction model

1. **Pan / zoom** the stage view. Tiles load in the background (async worker thread) so the GUI never stalls.
2. **Zoom out** over a large mosaic — the engine auto-selects a pyramid level so you see thumbnails, not full-res reads you'd never see.
3. **Shift+drag** a rectangle to select FOVs. Selected tiles get Cephla-blue borders.
4. **Click Run** on a processing tab. If nothing is selected, it runs on every FOV in the region. If you selected tiles, it runs on just those.
5. Processing phases animate live: flatfield samples calibration tiles then applies; stitcher registers adjacent pairs then re-lays them with green borders.

### Adding a new algorithm

One folder. One file. See [`.claude/skills/cephla-algorithm-absorber.md`](.claude/skills/cephla-algorithm-absorber.md) for the 9-step absorption protocol an agent follows to turn an external repo into a plugin: audit → create module → copy algorithm → write plugin wrapper → strip IO → declare deps → tests → memory safety → verify.

The plugin ABC is in `squid_tools/processing/base.py` — implement `parameters`, `validate`, `process` (and optionally `process_region`, `run_live`), `default_params`, `test_cases` and the app picks it up via Python entry points.

---

## v1 status

Each row is a self-contained feature merged to master.

<!--- KEEP THIS TABLE IN SYNC WITH docs/superpowers/specs/2026-04-09-squid-tools-v1-design.md --->

### Core (v1 IN, merged before this cycle)
- Namespace packages (`core`, `viewer`, `processing/flatfield`, `processing/stitching`, `app`)
- Continuous-zoom vispy viewer
- Multi-channel additive composite with per-channel colormaps
- 3 format readers (OME-TIFF, individual images, Zarr)
- Memory-safe data flow: LRU cache, TiffFile handle pool, viewport-only contrast
- Processing plugin ABC + entry-point discovery
- AppController, controls, region selector, processing tabs, log panel
- OME sidecar output
- Dev mode (`--dev`)
- CLI entry point, GPU runtime detection, PyInstaller spec
- ruff + mypy, unit + integration tests
- Selection model + live processing (Cycle A)
- Algorithm Absorber skill (`.claude/skills/cephla-algorithm-absorber.md`)

### This pass (Cycles B through G, all merged)

| Cycle | Title | Status | Key files |
|---|---|---|---|
| B | Production logger | ✅ | `squid_tools/logger.py`, `LogPanel` |
| C | Async tile loader | ✅ | `squid_tools/viewer/tile_loader.py`, `ViewerWidget._refresh` |
| D | Multi-scale pyramid zoom | ✅ | `squid_tools/viewer/pyramid.py`, `ViewportEngine._pick_level` |
| E | 3D data pipeline + canvas | ✅ partial | `squid_tools/viewer/volume_canvas.py`, `scripts/view_volume.py` |
| F | GPU compositing (CuPy fallback → numpy) | ✅ | `squid_tools/viewer/compositor.py` |
| G | R2 hosting (upload CLI + client) | ✅ partial | `squid_tools/remote/r2_client.py`, `scripts/upload_acquisition_to_r2.py` |

### v1 closure (Cycles H through P — **in progress, this run**)

| Cycle | Title | Status | Notes |
|---|---|---|---|
| H | Viewer polish (contrast, sliders, layout, copy) | ⏳ | Addresses macOS-test feedback |
| I | Stitcher correctness | ⏳ | Unify registration paths, verify tile shifts |
| J | Absorber v2 (GUI param manifest) | ⏳ | Captures source GUI's default+exposure decisions |
| K | Absorb Deconvolution | ⏳ | `_audit/Deconvolution` → `processing/decon/` |
| L | Absorb Phase from Defocus | ⏳ | `_audit/phase_from_defocus` |
| M | Absorb aCNS denoising | ⏳ | Calibrate-then-apply |
| N | Absorb background subtraction | ⏳ | sep.Background |
| O | 3D widget integration | ⏳ | Qt wrapper around `Volume3DCanvas` |
| P | Browser viewer | ⏳ | HTML/JS streaming from R2 |

Update: <!-- LAST-STATUS -->cycles in progress<!-- /LAST-STATUS -->

---

## Screen recordings

<!-- SCREEN-RECORDINGS -->
_Placeholder — record these during your morning test pass._

- [ ] `recording/open-acquisition.mp4` — File > Open, watch channels + sliders populate, log console shows metadata
- [ ] `recording/pan-zoom-pyramid.mp4` — pan across a large mosaic; zoom out to see pyramid auto-select; zoom in to see full-res
- [ ] `recording/shift-drag-selection.mp4` — shift+drag to select FOVs; Cephla-blue borders; click Run Flatfield
- [ ] `recording/run-stitcher.mp4` — click Run Stitcher; watch tile borders shift green as pairs register
- [ ] `recording/level-filter.mp4` — level-filter dropdown in log panel switches DEBUG ↔ INFO
- [ ] `recording/3d-volume-view.mp4` — launch `scripts/view_volume.py` on Linux, rotate a z-stack
- [ ] `recording/r2-upload.mp4` — set env vars, run the upload script, see keys listed
- [ ] `recording/dev-mode.mp4` — `python -m squid_tools --dev my_plugin.py` hot-loads a plugin
<!-- /SCREEN-RECORDINGS -->

---

## Technical details

### Repository layout

```
squid_tools/              # namespace package
├── logger.py             # setup_logging, short_tag (Cycle B)
├── __main__.py           # CLI entry point
├── core/
│   ├── data_model.py     # Pydantic models
│   ├── readers/          # OME-TIFF, individual, zarr
│   ├── cache.py          # MemoryBoundedLRUCache
│   ├── handle_pool.py    # TiffFile handle LRU
│   ├── pipeline.py
│   ├── sidecar.py        # OME sidecar manifest
│   ├── registry.py       # Plugin discovery via entry points
│   └── gpu.py            # CUDA runtime detection
├── viewer/
│   ├── canvas.py         # vispy StageCanvas (2D)
│   ├── volume_canvas.py  # vispy Volume3DCanvas (3D — Cycle E)
│   ├── compositor.py     # numpy + CuPy channel composite (Cycle F)
│   ├── pyramid.py        # stride-slicing downsample (Cycle D)
│   ├── tile_loader.py    # AsyncTileLoader (Cycle C)
│   ├── viewport_engine.py # spatial index + tile fetching + pyramid
│   ├── data_manager.py
│   ├── spatial_index.py
│   ├── selection.py
│   ├── colormaps.py
│   └── widget.py         # ViewerWidget (composes canvas + sliders + selection)
├── processing/
│   ├── base.py           # ProcessingPlugin ABC
│   ├── flatfield/        # BaSiCPy-based correction
│   └── stitching/        # TileFusion-derived pairwise + global opt
├── remote/
│   └── r2_client.py      # Cloudflare R2 client (Cycle G)
└── gui/
    ├── app.py            # MainWindow
    ├── controller.py
    ├── controls.py
    ├── region_selector.py
    ├── processing_tabs.py
    ├── log_panel.py      # status bar + scrollable console + level filter
    ├── algorithm_runner.py # QThread-based plugin runner
    ├── dev_panel.py      # hot-load plugins
    └── style.py
scripts/
├── view_volume.py               # 3D volume launcher (Cycle E)
└── upload_acquisition_to_r2.py  # R2 upload CLI (Cycle G)
tests/
├── unit/                        # ~320 tests
└── integration/                 # ~25 tests
docs/superpowers/
├── specs/                       # design docs per cycle
└── plans/                       # TDD task breakdowns
.claude/skills/
└── cephla-algorithm-absorber.md # 9-step absorption protocol
```

### Key mechanisms

- **Continuous zoom viewer.** One canvas, no mode switching. The viewport engine consults a grid-based spatial index for O(1) FOV lookup, picks a pyramid level from the viewport/screen ratio (`_pick_level`), and returns a list of composite tiles ready for the canvas to paint.
- **Async tile loading.** `AsyncTileLoader` owns a QThread + worker. Every pan/zoom `_refresh()` posts a request; the worker runs `get_composite_tiles` off the GUI thread and emits `tiles_ready` back. Replace-semantics: the latest request wins at both the worker and the GUI-side `_last_applied_id` filter. In tests, the loader flips to a synchronous mode (via `AsyncTileLoader._async_default = False` in `tests/conftest.py`) to avoid Qt thread-teardown races.
- **Multi-scale pyramid.** `_pyramid_cache` keyed by `(fov, z, channel, t, level)`. Level 0 bypasses the cache; levels 1–5 are `frame[::2**L, ::2**L].copy()`. Cache is cleared on acquisition load.
- **Multi-channel composite.** `compositor.composite_channels(frames, clims, colors_rgb)` on numpy by default; if CuPy imports and passes a 2x2 smoke test at module import, CuPy is used. Runtime CuPy failures fall back to numpy with a single WARNING.
- **Logging.** `setup_logging()` attaches a `RotatingFileHandler` (10 MB × 5) at `~/.squid-tools/logs/` (tempdir fallback). The GUI's `LogPanel` attaches a `QtLogHandler` that marshals records through a Qt signal to the GUI thread. Level filter: DEBUG / INFO / WARN / ERROR.
- **Processing plugins.** Entry-point discovery (`[project.entry-points."squid_tools.plugins"]`). Each plugin declares its params (Pydantic), validates against an acquisition, has a `process(frame) -> frame` for per-tile transforms and optionally `process_region(frames, positions) -> fused` for spatial algorithms. The `run_live(selection, engine, params, progress)` hook gives the plugin control over its own live behavior (flatfield: calibrate-then-apply; stitcher: progressive pairwise).
- **Algorithm absorber.** A skill file that teaches an agent how to integrate an external repo as a plugin. 9 steps: audit source → create module → copy algorithm → plugin wrapper → strip IO → dependencies → tests → memory safety → verify in dev mode.
- **3D rendering.** `Volume3DCanvas` wraps vispy's `Volume` visual + `TurntableCamera`. Data path: `ViewportEngine.get_volume(fov, channel, timepoint, level)` stacks z-planes into `(Z, Y, X)`. Multi-channel display layers one Volume per channel with its own colormap (additive via translucent blending).
- **R2 hosting.** `R2Client` wraps boto3 S3 with Cloudflare's endpoint. `upload_dir(local, prefix)` walks the acquisition tree preserving structure. `presigned_get_url(key, expires_in)` yields short-lived URLs for the browser viewer.

### Testing

```bash
pytest -q         # ~370 tests pass on master
ruff check squid_tools tests scripts
```

CI gates: ruff, mypy (strict), pytest. PyInstaller smoke tests (`installer/smoke_test.py`) exercise the frozen exe.

### Performance notes

- LRU cache default: 256 MB for raw frames.
- Handle pool default: 128 open TiffFiles.
- Pyramid: max 5 levels (1/32 scale), in-memory only (disk-backed pyramid deferred to v2).
- Async loader: single worker thread per viewer; replace-semantics drops stale requests.
- GPU compositing: opt-in via CuPy install. Not auto-required; numpy path is the safe default.

---

## License

See `LICENSE` (if present).

## Acknowledgements

- Built on [vispy](https://vispy.org), [PySide6](https://doc.qt.io/qtforpython-6/), [BaSiCPy](https://github.com/peng-lab/BaSiCPy), [tifffile](https://github.com/cgohlke/tifffile), [zarr](https://zarr.readthedocs.io), [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html).
- Algorithm absorptions derived from Cephla-Lab's [image-stitcher](https://github.com/Cephla-Lab/image-stitcher), [stitcher](https://github.com/Cephla-Lab/stitcher), and related repos.
