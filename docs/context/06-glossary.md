# Glossary + Conventions

Field-specific and project-specific terms. A fresh AI should read
this before attempting a reply.

---

## Microscopy / imaging

- **FOV** — field of view. One tile of a multi-tile mosaic, captured
  at one stage position.
- **Mosaic** — the assembled grid of FOVs covering a region.
- **Region** — a named area in the acquisition (e.g. well "A1" in a
  wellplate, or an arbitrary label like "manual" for free-form scans).
- **Z-stack** — multiple planes captured at different focal depths
  for the same FOV.
- **Time series** — multiple timepoints (`T`) of the same acquisition.
- **Channel** — one fluorescence / brightfield acquisition. In our
  datasets, channels named like `Fluorescence_405_nm_Ex`,
  `Fluorescence_488_nm_Ex`, etc.
- **ADU** — analog-to-digital unit. Raw camera count value, usually
  uint16 (0-65535 range).
- **Pixel size** — `µm/px` at the specimen plane. Derived from
  objective magnification, sensor pixel size, tube lens, binning.
- **NA** — numerical aperture of the objective.
- **PSF** — point spread function. The blur kernel of the optical
  system.
- **Airy disk** — diffraction-limited PSF. Radius ≈ 0.61 × λ / NA.

## Squid-specific

- **Squid** — Cephla-Lab's open hardware microscope platform.
- **acquisition.yaml** — Squid's metadata file.
- **coordinates.csv** — per-FOV stage coordinates.
- **acquisition parameters.json** — sensor + optics params.
- **Squid output formats** — three: OME-TIFF, Individual Images,
  Zarr. All three have corresponding readers in `core/readers/`.
- **BF LED matrix** — brightfield LED array used for quantitative
  phase illumination.
- **APA102** — the LED driver for the BF matrix, with tuned
  wavelength + illumination-NA defaults.

## Processing categories (umbrella terms on tabs)

- **Shading** — illumination correction (flatfield).
- **Denoising** — noise suppression (aCNS, future BM3D/NLM).
- **Background** — non-cell/object background subtraction
  (sep.Background, future sep.extract).
- **Deconvolution** — PSF-aware sharpening (Richardson-Lucy, OMW).
- **Phase** — quantitative phase retrieval from defocus.
- **Stitching** — tile registration + fusion (TileFusion-derived).
- **Segmentation** — v2: cell / object segmentation (StarDist,
  CellPose).
- **Tracking** — v2: cell tracking across timepoints.

## Processing algorithm names (inside an umbrella)

- **BaSiC** — the algorithm behind Flatfield; from peng-lab/BaSiCPy.
- **TileFusion** — maragall/stitcher's stitching + fusion kernels.
- **PetaKit5D** — reference for OMW + Richardson-Lucy deconvolution.
- **waveorder** — reference for phase-from-defocus reconstruction.
- **aCNS** — analytical correction with dark-frame sigma (Cephla's
  in-house denoiser).
- **sep** — Source Extractor Python, used for background subtraction.

## Reference repos in `_audit/`

- **ndviewer_light** — Cephla's napari-wrapping viewer. Reference
  for plane cache, channel composite mode, contrast limits,
  colormap decisions.
- **image-stitcher** — Cephla HCS viewer + flatfield GUI + wellplate
  grid. Reference for multi-plate layouts.
- **stitcher** (maragall/stitcher) — the TileFusion package. Source
  of stitching algorithms + pairwise registration + global opt +
  fusion kernels.
- **Deconvolution** (petakit5D) — OMW + RL engines. Partial port.
- **phase_from_defocus** — waveorder-based phase retrieval.
- **Squid** — acquisition firmware + software. Defines format.
- **ndviewer** — older Cephla viewer (pre-ndviewer_light).

## GUI / UX references

- **NIS Elements** — Nikon's microscopy suite. Pattern source for
  right-click context menus, ribbon tabs, double-click nested
  menus. Key invariant: no deep menu nesting.
- **Araceli Endeavor** — tissue HCS platform. Pattern source for
  wizard / step-based linear pipelines.
- **Revvity Harmony** — HCS analysis suite. Pattern source for
  drag-pipeline builder, well-plate heatmap, hover previews, top
  toolbar mode switching.
- **napari** — Python image viewer. Reference for composite mode,
  colormap application, contrast limits UX. Not a runtime dep.

## Architecture / book references

- **AOSA** — Architecture of Open Source Applications. Open source
  book the user expects the AI to consult. Project chosen pattern:
  **Eclipse RCP plugin architecture**.
- **Eclipse RCP** — Rich Client Platform. Plugin model: each plugin
  = self-contained package with declarative manifest + extension
  points.
- **Five Eclipse-RCP invariants** (from audit) that squid-tools
  should honor:
  1. Plugin = self-contained package
  2. Registry = single source of truth
  3. Extension points = formal hooks
  4. Stateless service interfaces
  5. Declarative configuration over code

## Code conventions

- **Plugin** — instance of `ProcessingPlugin` ABC. Registered via
  entry points, discovered by `PluginRegistry`.
- **`plugin.process(frame, params)`** — per-tile transform.
- **`plugin.process_region(frames, positions, params)`** — spatial
  operation on all FOVs (stitching).
- **`plugin.run_live(selection, engine, params, progress)`** — hook
  for live processing; plugin controls its own orchestration.
- **`plugin.default_params(optical)`** — derive params from
  acquisition metadata. Should raise if required metadata missing.
- **`plugin.test_cases()`** — synthetic inputs for automated testing.
- **`gui_manifest.yaml`** — per-plugin GUI parameter manifest.
- **Category** — umbrella term on the processing tabs. Stored on
  the plugin class as `category = "shading"` etc.
- **FOVPosition** — `(fov_index, x_mm, y_mm)` Pydantic model.
- **Acquisition** — top-level Pydantic model aggregating format,
  objective, channels, regions, z_stack, time_series, optical.

## Cache / memory

- **LRU cache** — `core/cache.py:MemoryBoundedLRUCache`. Bytes-
  bounded (256 MB default). Thread-safe. Stores raw frames.
- **Handle pool** — `core/handle_pool.py`. TiffFile handle LRU (128
  max). Thread-safe, per-file locks.
- **Display cache** — `ViewportEngine._display_cache`. Pre-composited
  RGB tiles keyed by `(fov, level, channels, z, t)`.
- **Pyramid cache** — `ViewportEngine._pyramid_cache`. Downsampled
  per-channel frames keyed `(fov, z, c, t, level)`.
- **Spatial index** — `viewer/spatial_index.py:SpatialIndex`. Grid-
  based O(1) FOV lookup by mm coordinates.

## Cycle naming

- **Cycle A** — Selection model + live processing (pre-session).
- **Cycle B-G** — This session's first build-up.
- **Cycle H-P** — Convergence cycles.
- **Cycles** are labeled alphabetically within a theme; v2 cycles
  likely use thematic prefixes (A1, B1, etc. matching the v2
  spec's priority categories).

## File conventions

- **Specs** → `docs/superpowers/specs/YYYY-MM-DD-name.md`
- **Plans** → `docs/superpowers/plans/YYYY-MM-DD-name.md`
- **Audits** → `docs/superpowers/audits/YYYY-MM-DD-name.md`
- **Tests** → `tests/unit/` (~370 tests) + `tests/integration/` (~30)
- **Scripts** → `scripts/` (standalone launchers + CLI tools)
- **Reference repos** → `_audit/` (git-ignored)
- **Feature worktrees** → `.worktrees/` (git-ignored)

## Commit message format

```
<type>(<scope>): <subject>

<body explaining WHY, not what>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

Types: `feat`, `fix`, `docs`, `test`, `chore`, `style`, `refactor`,
`perf`, `build`, `ci`.

Scopes (common): `viewer`, `gui`, `processing`, `core`, `stitcher`,
`flatfield`, `logger`, `compositor`, `pyramid`, `tile_loader`,
`remote`, `webdemo`, `absorber`, `v1`, `audit`, `docs`.

## Versioning

Per-package (when split): each `processing/<name>/` gets its own
version; the meta-package pins compatible ranges.

Current:
- `squid-tools` meta = `1.0.0`.
- Each processing sub-package's version tracked in its own
  `pyproject.toml` (if present).

## Formats (data)

Frame dtype coming out of readers: usually `uint16` (raw ADU).
Compositor converts to `float32` before blending. Output from
compositor: `(H, W, 3)` RGB `float32` in `[0, 1]`.

Pyramid frames: same dtype as source (uint16), with shape divided
by 2**level on YX axes.

Volumes: `(Z, Y, X)` of the same dtype as 2D frames.

RGBA volumes: `(Z, Y, X, 4)` float32 in [0, 1]. Alpha = per-voxel
max normalized intensity across channels.

## Qt conventions

- Widgets use `@property` for read-only view-state (e.g.
  `pixel_size_um`, `tile_size_mm`).
- Signals defined at class level (e.g. `selection_changed =
  Signal(set)`).
- Every QThread-owning widget has a test-time sync mode (see
  Bug #1 in `05-bug-recurrences.md`).
