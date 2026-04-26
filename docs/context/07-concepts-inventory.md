# Concepts Inventory

A dense index of every concept surfaced during this session. Scan
here when you need a quick map of the landscape; follow the pointers
into `references/specs/` or other context docs for depth.

**Flag:** if you spot a concept the user mentioned that is NOT on
this list, add it. The user said "so many concepts that I forgot
lots of stuff" — this page is the scan surface.

---

## A. Architecture

- **Namespace packages** — `squid_tools.*` shared across sub-
  packages that each have their own `pyproject.toml`.
- **Plugin ABC** (`processing/base.py:ProcessingPlugin`) — contract
  for every algorithm.
- **Entry-point discovery** (`core/registry.py`) — plugins listed
  under `[project.entry-points."squid_tools.plugins"]`.
- **Category + algorithm model** — plugin's `category` groups it
  under an umbrella tab; `name` is the specific algorithm.
- **Dependency management** — core + optional extras per plugin,
  designed in `references/specs/2026-04-21-v1-dependency-management.
  md`.
- **AOSA Eclipse RCP** — the formal architecture pattern.
- **Five RCP invariants** — plugin self-contained, registry as SoT,
  extension points, stateless services, declarative config.

## B. Data model + metadata

- **Acquisition** (Pydantic) — top-level. Reads from acquisition.yaml
  + coordinates.csv + format-specific files.
- **ObjectiveMetadata** — name, magnification, NA, pixel_size_um,
  sensor, binning, tube_lens.
- **OpticalMetadata** — modality, immersion, NA, pixel_size_um,
  dz_um. Cross-populated from objective via `model_post_init`.
- **AcquisitionChannel** — per-channel config (name, wavelength,
  exposure, z_offset).
- **Region** + **FOVPosition** — spatial organization of FOVs.
- **ZStackConfig** — nz, delta_z_mm, reference plane.
- **TimeSeriesConfig** — nt, delta_t_s.
- **Three Squid formats** — OME_TIFF, INDIVIDUAL_IMAGES, ZARR.
  Legacy support commitment: support for the next ~year.
- **Auto-reader generator** (v2) — generate FormatReader from a
  YAML spec.
- **OME schema validation** (v2) — validate sidecar + exports
  against OME-XML XSD.
- **Media Cybernetics interop** (v2) — reverse-engineer their
  metadata.

## C. Viewer

- **Continuous-zoom stage view** — one canvas, no mode switching.
- **Multi-scale pyramid** — level 0 full-res; levels 1-5 at
  2^L decimation.
- **Viewport engine** — spatial index + pyramid + tile fetching.
- **Async tile loader** — worker QThread with replace-semantics.
- **Compositor** — CPU numpy composite (optional CuPy). Pre-
  renders RGB tiles.
- **Dual-mode compositor** (v2) — CPU for zoomed-out / per-channel
  GPU layers for live viewport.
- **Square canvas** — `SquareContainer` widget, analytical geometry.
- **Navigator pane** (v2) — persistent mini-map with viewport rect.
- **3D volume rendering** — vispy Volume visual + TurntableCamera.
- **WebGL VolumeVisual port** (v2 stretch) — 3D in the browser.
- **Real-time acquisition streaming** (v2 stretch) — live tiles
  during acquisition.

## D. Processing plugins

- **Flatfield (BaSiC)** — shading correction.
- **Stitcher** (TileFusion) — pairwise + global opt + fusion.
- **Deconvolution** (RL + Gaussian PSF, 2D per-tile).
- **Phase from Defocus** (waveorder-based, stub in v1).
- **aCNS** — analytical denoiser with dark-frame sigma.
- **sep.Background** — per-tile background estimation.
- **Cell segmentation** (v2) — StarDist / CellPose / in-house U-Net.
- **Magical brush** (v2) — paint rough, model refines.
- **Cell tracking** (v2) — transfer-learned tracker across time.
- **Object detection** (v2) — YOLO-style box detector.
- **Smart Acquisition (CRUK 3D)** (v2 stretch) — closed-loop
  acquisition control.
- **Quantitative phase reconstruction** — full waveorder integration
  (v2; currently stub).
- **Volumetric deconvolution** — OMW from PetaKit (v2; currently
  2D-only).
- **Per-pixel dark-frame calibration** (v2) — replaces aCNS scalar
  params with calibration maps.

## E. Absorption loop + dev environment

- **Squid-Tools is the development environment for absorbed
  algorithms** — once a repo is absorbed, its upstream is a frozen
  reference (in `_audit/`) and the active development of that
  algorithm happens inside `squid_tools/processing/<name>/`. No
  round-tripping. The absorber + dev mode together make the loop:
  pull repo into `_audit/`, run absorber, iterate inside the plugin
  using `--dev` against real data.
- **Algorithm Absorber skill** — 9-step protocol at
  `.claude/skills/cephla-algorithm-absorber.md`.
- **gui_manifest.yaml** — per-plugin GUI parameter manifest
  capturing source repo's scientific wisdom.
- **Step 4.5** — capture the source GUI's manifest (added in
  Cycle J).
- **Dev mode** — `python -m squid_tools --dev <plugin.py>` hot-
  loads a plugin.
- **Test cases** — each plugin ships `test_cases()` returning
  synthetic inputs.
- **85% auto-ported rule** — user's claim that the absorber handles
  ~85% of the work for any new algorithm repo.
- **Agentic regression runner** (v2) — agent that reviews every PR
  against the functional test plan.
- **Three-node dev-absorb-demo network** (v2) — dev machine, R2 +
  CI, web demo.

## F. Live processing behavior per category

From the v1 spec:

- **Calibrate-then-apply** (shading, denoising) — sample random
  tiles, compute profile, apply per tile.
- **Progressive pairwise** (stitching) — register pairs one by one
  with live tile shifts.
- **Tile-by-tile iterative** (deconvolution, object detection) —
  process each tile independently with live overlays.
- **Per-FOV volumetric** (phase, 3D) — z-stack per FOV.
- **Track accumulation** (tracking) — user picks a cell, track
  extends forward + backward in time.
- **Paint-refine** (segmentation brush) — user paints rough, model
  refines, live overlay.

## G. GUI

- **MainWindow** — composition root.
- **ControlsPanel** — FOV borders toggle.
- **ProcessingTabs** — category-umbrella tabs with vertical layout
  (TabPosition.West).
- **RegionSelector** — wellplate grid or region dropdown.
- **LogPanel** — scrollable console with level filter + memory /
  GPU / cache status bar.
- **Viewer3DWidget** — Qt wrapper for Volume3DCanvas.
- **Processing tab compact mode** — toggle + Run + status on one
  row.
- **SquareContainer** — centers + squares its child via geometry.
- **Per-channel contrast slider** — one slider per channel (max
  clim); auto button resets + re-enables viewport-follow.
- **Auto-contrast viewport follow** — debounced recompute on pan
  for untouched channels.
- **Right-click menu items** — Fit View, Toggle Borders, Open 3D
  View…, Export Stitched Region…
- **Checkbox installer UI** (v2) — downloads custom bundle based
  on selected modules.
- **Viewer preferences panel** (v2) — default colormaps, clims,
  pyramid aggressiveness, border style.
- **Acquisition comparison** (v2) — side-by-side split view.
- **Annotation tools** (v2) — polygon / brush / freehand → geojson.
- **Ribbon vs tabs vs wizard** — UX tension between NIS Elements,
  Araceli, Revvity patterns.

## H. Infrastructure

- **Production logger** — Python logging with rotating file +
  QtLogHandler + level filter.
- **Memory-bounded LRU cache** — for raw frames (256 MB default).
- **TiffFile handle pool** — 128 handles, per-file locks.
- **Spatial index** — grid-based O(1) FOV lookup (R-tree in v2).
- **Tile prefetch** (v2) — speculatively load tiles one ring out.
- **Disk-backed pyramid** (v2) — persistent `.squid-tools/pyramid/`
  store.
- **Zero-copy dask slab reads** (v2) — for very large OME-TIFF.
- **OME sidecar** — `.squid-tools/manifest.json` with ProcessingRun
  entries per run.
- **AsyncTileLoader async_mode flag** — enables sync mode in tests.

## I. Compositing + contrast

- **CPU compositor** — pre-composites RGB tiles on CPU. Scales.
- **CuPy compositor** — GPU-accelerated per the numpy path. Auto-
  selected at import via a 2×2 smoke test.
- **napari-style composite mode** (v2) — per-channel layers,
  additive blending, GPU-side.
- **Auto-contrast** — samples FOVs, returns (p1, p99) + records
  actual max.
- **Viewport-follow contrast** — 500ms debounced recompute on pan.
- **User-tuned channel pinning** — moving a slider marks the
  channel untouched-by-auto.
- **Per-channel colormap** — hex + RGB tuples in `viewer/colormaps.
  py`, with wavelength → name mapping.

## J. Storage / remote

- **R2Client** — Cloudflare R2 upload via boto3.
- **R2 as pip index** (v2) — simple layout for module wheels.
- **Cloudflare Pages** — download page hosting target (v2).
- **Presigned URLs** — for the browser viewer to access private
  buckets.
- **Three-node network** (v2 F3) — dev (Mac) + cloud (R2) + web
  demo.

## K. Distribution

- **Per-module pip extras** — `squid-tools[stitching,decon]`.
- **Convenience bundles** — `all-corrections`, `all-restoration`,
  `everything`.
- **Installer app** (v2 A2) — PySide6 wizard with checkboxes.
- **modules.json** (v2) — manifest served from R2 with sizes +
  descriptions.
- **CI wheel publishing** (v2 F1) — GH Actions rebuilds on every
  commit, uploads to R2.
- **Web download page** (v2 A1) — Cloudflare Pages site.

## L. Testing

- **Per-cycle TDD** — tests in the plan, not the spec.
- **Full-product functional test plan** (v2 G1) — end-to-end user
  workflows, covers every format + every plugin + performance
  regression on synthetic petabyte dataset.
- **Agentic regression runner** (v2 G2) — PR review bot.
- **pytest-qt** — widget testing with qtbot fixture.
- **qtbot addWidget weakref pitfall** — see bug recurrences.
- **Sync-mode test fixtures** — for any QThread-owning widget.

## M. Programmatic surface

- **MCP API server** (v2 E1) — Model Context Protocol server
  exposing plugin + viewer API.
- **Scriptable pipelines** (v2 E2) — YAML/JSON chains of plugins.
- **Pipeline tab** (v2) — GUI for building chains via UI.
- **Dev mode hot-load** — already shipped.

## N. Scale

- **Petabyte-scale** — design constraint the user repeats. Every
  large-data change is benchmarked against this.
- **Agentic scaling** — N algorithms × M suites via the absorber.
- **Tile-by-tile viewport** — user only sees what's in viewport;
  engine only reads those tiles.

## O. Collaboration + working style

- **Ground every change in file:line** — rule for all AI-suggested
  changes.
- **Port before reinvent** — reflex to check `_audit/` first.
- **No hardcoded values** — plugins raise if metadata missing.
- **Small batches** — one concern per commit.
- **No shortcuts** — fix things properly, don't cut corners under
  feedback pressure.
- **Screenshots as evidence** — user describes what they see;
  trust the description.

## P. Project lifecycle

- **v1** — current, tagged `v1.0.0`. Converged.
- **v2** — spec at `references/specs/2026-04-21-v2-design.md`.
- **Reinvention audit** — `references/audits/2026-04-21-reinvention-
  audit.md`.
- **Convergence pass** — final push before v1 tag (Cycles H-P +
  convergence).

## Q. Things the user mentioned that I may have underindexed

**Be honest:** I'm certain these exist but I don't have strong
coverage. When the user reviews this file, they may call out
items I missed or got wrong.

- The specific commercial GUIs' interaction minutiae (e.g. what
  exactly Araceli's wizard looks like, which Revvity widgets the
  user finds indispensable).
- The "customer interview" user flow for the installer (user
  described this; scope is drafted but UX details are thin).
- The three-node network's exact orchestration (git push → CI →
  R2 → download page refresh → web demo refresh).
- Legacy format quirks beyond the three listed.
- The "analytical" part of aCNS (what specifically the dark-frame
  noise model is vs just bias + sigma).
- The "Cephla-Lab channel conventions" (wavelengths, standard
  fluorophore mapping, colormap norms).
- Licenses / commercial terms for the software.
- The embeddable mode — `gui/embed.py` stub exists for embedding
  in Squid's own GUI; not exercised.
- Style system (Cephla palette in `gui/style.py`). Token set
  defined in v1 spec but not centralized as a theme API.

If the user reads this and flags an item I missed, append it to
this list with a pointer to where it should go.
