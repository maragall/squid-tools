# Project State — as of 2026-04-21

## One-line
PySide6 + vispy desktop viewer / post-processing connector for
Cephla-Lab/Squid microscopy acquisitions, with a plugin-based
architecture for algorithm absorption.

## Status
`v1.0.0` tagged on master. 402 tests passing. ruff clean. Actively
being tested by the user on a real 70-FOV 4-channel 10x mouse brain
acquisition. Multiple v2 items identified but not blocking the v1
release candidate.

## Repository layout

```
squid_tools/
├── logger.py                     # setup_logging, short_tag (Cycle B)
├── __main__.py                   # CLI: python -m squid_tools [path]
├── core/
│   ├── data_model.py             # Pydantic v2 models; Acquisition.model_post_init
│   │                              # cross-populates optical from objective
│   ├── readers/                  # OME-TIFF, Individual, Zarr (detect_reader)
│   ├── cache.py                  # MemoryBoundedLRUCache (thread-safe, bytes-bounded)
│   ├── handle_pool.py            # TiffFile handle pool with LRU eviction
│   ├── pipeline.py               # Ordered list of per-tile transforms
│   ├── sidecar.py                # .squid-tools/manifest.json writer
│   ├── registry.py               # PluginRegistry + entry-point discovery
│   ├── gpu.py                    # CUDA runtime detection
│   └── gui_manifest.py           # gui_manifest.yaml loader (Cycle J)
├── viewer/
│   ├── canvas.py                 # vispy StageCanvas (2D)
│   ├── volume_canvas.py          # vispy Volume3DCanvas (3D, Cycle E)
│   ├── square_container.py       # Geometric-center helper (GUI)
│   ├── compositor.py             # numpy + CuPy fallback channel compositor (Cycle F)
│   ├── pyramid.py                # stride-slicing downsample, MAX_PYRAMID_LEVEL=5 (D)
│   ├── tile_loader.py            # AsyncTileLoader (Cycle C; async_mode flag)
│   ├── viewport_engine.py        # spatial index + tile fetching + pyramid + contrast
│   ├── data_manager.py
│   ├── spatial_index.py          # grid-based O(1) FOV lookup
│   ├── selection.py              # SelectionState QObject (Cycle A)
│   ├── colormaps.py              # wavelength → hex + RGB mappings
│   ├── widget.py                 # ViewerWidget (canvas + sliders + selection)
│   └── widget_3d.py              # Viewer3DWidget (Qt wrapper for 3D, Cycle O)
├── processing/
│   ├── base.py                   # ProcessingPlugin ABC
│   ├── flatfield/                # BaSiC-based illumination correction
│   ├── stitching/                # TileFusion: pair-finding + registration +
│   │                              # global opt + Numba-JIT fusion kernels
│   ├── decon/                    # Richardson-Lucy + Gaussian PSF (Cycle K)
│   ├── phase/                    # Phase-from-defocus parameter surface (Cycle L)
│   ├── acns/                     # Analytical scalar denoiser (Cycle M)
│   └── bgsub/                    # sep.Background subtractor (Cycle N)
├── remote/
│   └── r2_client.py              # Cloudflare R2 upload client (Cycle G)
├── webdemo/
│   └── viewer.html               # Static Canvas2D browser viewer (Cycle P)
└── gui/
    ├── app.py                    # MainWindow (layout + menus + run wiring)
    ├── controller.py             # AppController (owns acquisition + registry)
    ├── controls.py               # ControlsPanel (FOV borders checkbox)
    ├── region_selector.py        # Wellplate / region dropdown
    ├── processing_tabs.py        # Category-grouped plugin tabs
    ├── log_panel.py              # Scrollable log with level filter
    ├── algorithm_runner.py       # AlgorithmRunner QThread (Cycle A)
    ├── dev_panel.py              # Dev-mode hot-load console
    └── style.py                  # Cephla-palette QSS

scripts/
├── view_volume.py                # Standalone 3D volume launcher
├── upload_acquisition_to_r2.py   # R2 upload CLI
└── build_browser_bundle.py       # Bundles viewer.html + PNGs + tiles.json

tests/
├── unit/       # ~370 tests
└── integration/ # ~30 tests

docs/superpowers/
├── specs/      # 11 design specs
├── plans/      # 15 implementation plans
└── audits/     # reinvention audit vs _audit/ reference repos

.claude/skills/
└── cephla-algorithm-absorber.md  # 9-step absorber protocol (with Step 4.5
                                   # for gui_manifest.yaml capture, Cycle J)

_audit/                           # reference repos (ignored): ndviewer_light,
                                   # image-stitcher, stitcher, Deconvolution,
                                   # phase_from_defocus, Squid, ndviewer
```

## Architecture at a glance

- **Core.** Pure Pydantic v2 data model + lazy readers. No GUI dependency.
- **Viewer.** Custom vispy + PySide6 continuous-zoom stage view. Single
  canvas, no mode switching. Pyramid + async tile loader for scale.
- **Processing.** One plugin per algorithm, each in its own namespace
  package with a `pyproject.toml`, entry point, and `gui_manifest.yaml`.
- **GUI shell.** Thin PySide6 wrapper with left column (processing tabs +
  controls), center (square canvas), right (region selector), bottom
  (log panel).
- **Plugin discovery.** `registry.py` walks `[project.entry-points.
  "squid_tools.plugins"]`. Missing deps → plugin skipped; GUI shows only
  installed plugins.
- **Dependency management.** Meta-package + per-plugin optional extras
  (`pip install squid-tools[stitching,decon]`). Core-only by default.
  Design at `references/specs/2026-04-21-v1-dependency-management.md`.

## Plugin inventory

| Plugin | Package | Category | Pattern | Source ref |
|---|---|---|---|---|
| Flatfield (BaSiC) | `processing/flatfield` | shading | calibrate-then-apply | image-stitcher |
| Stitcher | `processing/stitching` | stitching | pairwise + global opt + fusion | maragall/stitcher tilefusion |
| Deconvolution | `processing/decon` | deconvolution | RL + Gaussian PSF | petakit5D (partial) |
| Phase from Defocus | `processing/phase` | phase | param surface only, reconstruction stub | waveorder |
| aCNS | `processing/acns` | denoising | scalar bias + σ threshold | (no ref — designed in v1 spec) |
| sep.Background | `processing/bgsub` | background | per-tile bg subtract | sep library |

## v1 IN (all landed)

- Namespace packages (core, viewer, processing/*, remote, webdemo, gui)
- Continuous-zoom vispy viewer with multi-scale pyramid (5 levels)
- Multi-channel additive composite (CPU compositor + CuPy fallback)
- 3 format readers (OME-TIFF, Individual, Zarr) unified through
  `Acquisition.model_post_init`
- Memory-safe data flow (256 MB LRU + 128-handle pool + viewport-only
  contrast)
- Processing plugin ABC with `process()`, `process_region()`,
  `run_live()`, `test_cases()`
- 6 absorbed plugins (see inventory above)
- Selection model (shift+drag on canvas)
- AlgorithmRunner QThread for progressive processing
- Async tile loader with replace-semantics
- OME sidecar manifest recording every run
- 3D volume rendering primitives + Viewer3DWidget
- Browser viewer (static HTML + Canvas2D + tiles.json)
- Cloudflare R2 upload client + script
- Production logger (rotating file + Qt handler + level filter)
- GUI manifest pattern (gui_manifest.yaml per plugin)
- Algorithm Absorber skill with 9-step protocol + Step 4.5 manifest
- ruff + mypy + 402 unit/integration tests

## v2 deferred (with priority)

See `references/specs/2026-04-21-v2-design.md` for full scope. P0/P1/P2/P3:

**P0** (close v1 loose ends):
- Web download page + CI wheel publishing to R2
- Checkbox installer UI
- PyInstaller hardening per-module
- Petabyte-scale optimizations (disk-backed pyramid, R-tree spatial
  index, tile prefetch, zero-copy dask)
- WebGL browser viewer upgrade
- Full-product functional test plan

**P1** (high-value algorithm coverage):
- Cell segmentation (StarDist / CellPose) + magical brush
- Cell tracking (transfer learning)
- Object detection
- Navigator pane
- Annotation tools (polygon / brush / freehand → geojson)
- MCP API server

**P2** (interop):
- Media Cybernetics metadata interop
- Auto-generated reader classes
- Formal OME schema validation
- Viewer preferences
- Acquisition comparison (side-by-side)
- Scriptable pipelines (YAML DSL)
- Three-node dev-absorb-demo network
- Agentic regression runner

**P3** (stretch / research):
- Smart Acquisition (CRUK 3D closed-loop)
- Real-time acquisition streaming
- WebGL VolumeVisual port
- Collaborative viewing

## Hotspots / known gaps

See `05-bug-recurrences.md`. Summary:

1. **Contrast auto-follow on pan** — shipped in final convergence
   (widget.py `_autocontrast_timer`). Uses real sampled max instead of
   2×p99 heuristic.
2. **Channel compositor on CPU** vs napari's GPU per-channel layer
   model — CPU compositor kept at user's request (scales to petabyte)
   but v2 should offer a dual-mode toggle.
3. **Pyramid × pipeline crash** — pipeline transforms skipped at
   level > 0 (documented in viewport_engine.py). v2 should downsample
   correction maps per level.
4. **Sidecar schema is thin** — ProcessingRun stores params + status
   but no input/output file hashes.
5. **Stitcher live path shows seams** — fusion kernels present
   (`process_region` + `fuse_region_to_array`) but only invoked via
   right-click "Export Stitched Region…". Live preview shows
   re-positioned tiles without blending.

## External references baked into the project

- `_audit/ndviewer_light/` — Cephla-Lab nd-viewer, the model for the
  plane cache + napari composite-mode patterns. Our viewer derives
  memory-safety ideas from here.
- `_audit/image-stitcher/` — Cephla-Lab HCS viewer + flatfield GUI.
  Reference for contrast + colormap conventions + parameter defaults.
- `_audit/stitcher/` — maragall/stitcher + TileFusion. Source of the
  stitcher plugin's pairwise registration + global opt + fusion kernels.
- `_audit/Deconvolution/` — PetaKit5D decon (OMW + RL). Partial port.
- `_audit/phase_from_defocus/` — waveorder-based phase. Parameter
  surface ported; reconstruction stub.
- `_audit/Squid/` — Cephla-Lab Squid acquisition firmware + software.
  Defines the three output formats we read.

## Tag history

- `v1.0.0` — current. First converged release candidate.

## Branch state

Single-branch workflow. Master is canonical. Feature branches in
`.worktrees/*` used during cycles, merged with `--no-ff`, deleted
after merge.
