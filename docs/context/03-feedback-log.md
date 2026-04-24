# Feedback Log

User-given feedback from testing sessions, paired with the fix (or
deferral). Reconstructed from commits + memory; not verbatim.

Ordered roughly chronologically within each category.

---

## GUI layout

| Symptom | Fix | Where | Status |
|---|---|---|---|
| Processing tabs ribbon took too much vertical space | Compact tabs: toggle+Run+status on one row; max height 170px | `gui/processing_tabs.py` `_PluginTab.__init__` | Shipped |
| Still too much; want left column not top ribbon | Moved ProcessingTabs to LEFT column, stacked over ControlsPanel | `gui/app.py` MainWindow layout | Shipped |
| Left column too wide (260px) | Max 190px + setMinimumWidth(0) + setChildrenCollapsible(True) | `gui/app.py` | Shipped |
| Tab labels horizontal still eats width | TabPosition.West (vertical labels) | `gui/app.py` `self.processing_tabs.setTabPosition(West)` | Shipped |
| "Enable {algo} in pipeline" copy confusing | "Apply {algo} to viewer" | `gui/processing_tabs.py` `_PluginTab` | Shipped |
| FOV borders ON by default was noisy | Off by default everywhere | `viewer/canvas.py` `_borders_visible=False`, `gui/controls.py` `setChecked(False)` | Shipped |
| Square canvas, center | `SquareContainer` widget (analytical geometry, no Qt layout) | `viewer/square_container.py` | Shipped |
| First attempt squared the whole ViewerWidget not the canvas | Moved SquareContainer inside ViewerWidget; wraps only the vispy native widget | `viewer/widget.py` | Shipped |
| Side columns asymmetric | Equal max widths on both sides | `gui/app.py` `side_col_px=190` | Shipped |
| Two columns of sliders per channel | Single slider per channel (max only); min pinned to auto p1 | `viewer/widget.py` `_build_channel_checkboxes` | Shipped |
| Sliders layout unprofessional | Tighter heights (14px), compact "auto" button, dropped value label | `viewer/widget.py` | Shipped |
| Umbrella terms should match field | Shading / Denoising / Background / Deconvolution / Phase / Stitching as tab categories | `gui/processing_tabs.py` `CATEGORY_LABELS` | Shipped |
| Plugin display names matched reference | "Flatfield (BaSiC)", "aCNS", "sep.Background" | Each plugin's `name` attribute | Shipped |

---

## Contrast / compositor

| Symptom | Fix | Where | Status |
|---|---|---|---|
| Flatfield crash at pyramid level > 0 (shape mismatch) | Skip pipeline transforms at level > 0 | `viewer/viewport_engine.py` `get_composite_tiles` | Shipped |
| Crash when all channels toggled off | Return empty tile list when active_channels empty | `viewer/viewport_engine.py` `get_composite_tiles` | Shipped |
| Incorrect channel blending | Root cause was flatfield crash cascade + stale display cache | Same as above + cache invalidation on channel toggle | Shipped |
| Contrast pegs at 2×p99, can't reach real bright pixels | Use engine's sampled max (`_last_sampled_max`) instead of heuristic | `viewport_engine.py:compute_contrast`, `widget.py:_apply_auto_contrast_to_channel` | Shipped |
| Pan to bright region doesn't adapt | 500ms debounce timer re-samples contrast for non-user-tuned channels | `widget.py` `_autocontrast_timer`, `_user_tuned_channels` | Shipped |
| Compositor reinvents napari's layer mode | Kept CPU compositor at user's request (petabyte scale); dual-mode deferred | `viewer/compositor.py` | v2 deferred |

---

## Stitcher

| Symptom | Fix | Where | Status |
|---|---|---|---|
| Right-click "Run registration" said "no pairs found" | Removed the engine path; toggle uses `plugin.run_live` via AlgorithmRunner | `gui/app.py` `_auto_run_stitcher` | Shipped |
| Registered tiles don't visibly shift | Was a display_cache invalidation issue; set_position_overrides now clears it | `viewport_engine.py` `set_position_overrides` | Shipped |
| Defaults don't match reference repo | Ported TileFusion.__init__ defaults (ssim_window=15, threshold=0.5, max_shift=100, blend_pixels=0, downsample_factor=1) | `processing/stitching/plugin.py` `StitcherParams` | Shipped |
| Hardcoded pixel_size_um=0.325 | Removed; pixel_size_um now required, derived from `acq.optical.pixel_size_um` | Same file | Shipped |
| Stitcher has no fusion (reference does) | Added `fuse_region_to_array` method + right-click "Export Stitched Region…" menu item | `processing/stitching/plugin.py` + `viewer/widget.py` `_export_stitched` | Shipped (partial — export-only, not live) |

---

## Metadata

| Symptom | Fix | Where | Status |
|---|---|---|---|
| Plugins hardcode pixel size / NA / wavelength | Plugins' `default_params` raise if metadata missing | All plugins' `default_params` | Shipped for Stitcher + Decon |
| Readers don't unify their `optical` shape | `Acquisition.model_post_init` cross-populates optical from objective | `core/data_model.py` | Shipped |
| OME sidecar exists but isn't populated | `_on_run_complete` / `_on_run_failed` append ProcessingRun to manifest.json | `gui/app.py` `_record_sidecar_run` | Shipped |
| Legacy format support | Three readers cover OME-TIFF, Individual, Zarr; auto-reader gen deferred | `core/readers/` | v2 C1 |

---

## Absorption loop

| Symptom | Fix | Where | Status |
|---|---|---|---|
| Absorbing loses source GUI's parameter decisions | `gui_manifest.yaml` per plugin; Step 4.5 of the absorber skill | `core/gui_manifest.py`, `.claude/skills/cephla-algorithm-absorber.md` | Shipped (Cycle J) |
| ProcessingTabs doesn't consume the manifest | `_PluginTab.__init__` loads it via `inspect.getfile(plugin.__class__)` | `gui/processing_tabs.py` | Shipped |
| Manifest should drive visibility + range + tooltip | Implemented: hidden params go to `_hidden_defaults`, visible ones get spinbox constraints | Same file | Shipped |

---

## Infrastructure / dependencies

| Symptom | Fix | Where | Status |
|---|---|---|---|
| Flat pyproject pulls every dep for every user | Split into core + optional extras per plugin | `pyproject.toml` | Shipped |
| Customer installer: click modules, get custom bundle | Design written; GUI impl deferred | `docs/superpowers/specs/2026-04-21-v1-dependency-management.md` | Design in v1; GUI in v2 A2 |

---

## Process / AI behavior

| Symptom | Fix | Status |
|---|---|---|
| AI looped on pytest after SIGABRT | Rule: max 2 runs per cycle; parse crash output; never retry blindly | Followed after user called it out |
| AI reinvented instead of porting | Reinvention audit + rule "check _audit/ first" | Shipped audit doc |
| Big specs before finishing current cycle | Rule: converge current before next | Followed after user called it out |
| Too many fixes in one commit | Rule: small batches, one concern per commit | Followed after user called it out |

---

## User-flagged things that are STILL open

- **Compositor dual-mode** (CPU for pyramid / napari-layer for live
  viewport) — v2 big item.
- **Disk-backed pyramid** — v2 C3.
- **R-tree spatial index** — v2 C3.
- **Tile prefetch** — v2 C3.
- **Web download page + CI wheel publishing** — v2 A1 + F1.
- **Checkbox installer UI** — v2 A2.
- **WebGL browser viewer** — v2 F2.
- **Segmentation + brush** — v2 B1.
- **Cell tracking** — v2 B2.
- **Smart Acquisition (CRUK 3D)** — v2 B4.
- **MCP API server** — v2 E1.
- **Media Cybernetics interop** — v2 B5.
- **Auto-reader generator** — v2 C1.
- **Navigator pane** — v2 D1.
- **Annotation tools** — v2 D2.
- **Stitcher fusion in LIVE view** (not just export) — v2 item.
- **Umbrella terms** — may need refinement (e.g. "Illumination" vs
  "Shading").
