# Squid-Tools v1 Design Spec

## Purpose

Squid-tools is the open-source post-processing companion for Cephla-Lab/Squid. It is a connector that wraps microscopy algorithms into a unified, data-intensive system that reads Squid's acquisition formats. It provides a visual GUI that requires zero training and a scriptable backend that Squid can call.

**Audience:** Life sciences researchers on Windows and Linux workstations. They do not know how to configure GPUs or install packages. The software must work out of the box. If it needs a manual, it has failed.

**Guiding principles:**
- Thin PySide6 GUI shell over a data-intensive core library with zero GUI dependencies
- Custom vispy+PySide6 viewer (no napari, no ndviewer_light dependency). PySide6 (Qt 6, LGPL) for commercial-grade HiDPI rendering, free for commercial use.
- Namespace packages for dependency isolation (each processing module is independently installable)
- Processing modules are pure algorithms: numpy arrays in, numpy arrays out
- Architecture designed for agentic scaling (an agent adds a module by creating one folder with one plugin.py)

---

## Architecture: Namespace Packages

One monorepo. Each component is an independently installable pip package sharing the `squid_tools` namespace.

```
squid-tools/                              # One git repo
├── core/                                 # squid-tools-core
│   ├── pyproject.toml
│   └── squid_tools/core/
│       ├── data_model.py                 # Pydantic v2 models
│       ├── readers/                      # OME-TIFF, Individual, Zarr readers
│       ├── cache.py                      # Memory-bounded LRU cache
│       ├── handle_pool.py               # TiffFile handle pool
│       ├── pipeline.py                   # Processing pipeline
│       ├── sidecar.py                    # OME sidecar manifest
│       ├── registry.py                   # Plugin discovery via entry points
│       └── gpu.py                        # GPU runtime detection
├── viewer/                               # squid-tools-viewer
│   ├── pyproject.toml
│   └── squid_tools/viewer/
│       ├── canvas.py                     # Vispy OpenGL tile rendering + colormaps
│       ├── data_manager.py              # Viewport-aware dask/cache loading
│       └── widget.py                     # QWidget: canvas + sliders + FOV/mosaic modes
├── processing/stitching/                 # squid-tools-stitching
│   ├── pyproject.toml
│   └── squid_tools/processing/stitching/
│       ├── plugin.py                     # StitcherPlugin(ProcessingPlugin)
│       ├── registration.py              # Phase cross-correlation + SSIM
│       ├── fusion.py                     # Numba-JIT weighted blending
│       ├── optimization.py              # Least-squares global positioning
│       └── utils.py                      # GPU/CPU xp abstraction
├── processing/flatfield/                 # squid-tools-flatfield
│   ├── pyproject.toml
│   └── squid_tools/processing/flatfield/
│       ├── plugin.py                     # FlatfieldPlugin(ProcessingPlugin)
│       └── correction.py                # BaSiCPy fitting + application
├── app/                                  # squid-tools (meta-package + GUI shell)
│   ├── pyproject.toml
│   └── squid_tools/
│       ├── __init__.py
│       ├── __main__.py
│       └── gui/
│           ├── app.py                    # MainWindow
│           ├── controller.py            # AppController
│           ├── controls.py              # Left panel
│           ├── region_selector.py       # Right panel
│           ├── processing_tabs.py       # Top tabs (auto-generated from plugins)
│           ├── log_panel.py             # Bottom status bar
│           └── embed.py                 # Embeddable widget for Squid
├── installer/
│   ├── entry.py                          # Frozen exe entry point
│   ├── smoke_test.py                     # Post-freeze smoke tests
│   └── squid_tools.spec                  # PyInstaller spec
└── tests/
```

### Package Dependencies

```
squid-tools-core:       pydantic>=2.10, numpy, dask[array], tifffile, pyyaml, zarr
squid-tools-viewer:     squid-tools-core, vispy, PySide6 (Qt 6, LGPL)
squid-tools-stitching:  squid-tools-core, numba, scikit-image, scipy, tensorstore
squid-tools-flatfield:  squid-tools-core, scipy (+ optional basicpy)
squid-tools (app):      squid-tools-core, squid-tools-viewer, PySide6
```

Users install: `pip install squid-tools[stitching,flatfield]`

Or download a pre-built .exe/.AppImage from the web page that bundles selected modules.

### Plugin Discovery

Each processing package declares an entry point:

```toml
[project.entry-points."squid_tools.plugins"]
stitcher = "squid_tools.processing.stitching.plugin:StitcherPlugin"
```

At runtime, `core/registry.py` discovers all installed plugins:

```python
for ep in importlib.metadata.entry_points(group="squid_tools.plugins"):
    plugin_cls = ep.load()
    registry.register(plugin_cls())
```

No central registry file. No import chains. Adding a module = one folder + one entry point.

---

## Processing Plugin ABC

Every processing module implements this interface. Pure algorithms: numpy in, numpy out.

```python
class ProcessingPlugin(ABC):
    name: str                    # Human-readable, shown in GUI tab
    category: str                # "stitching", "correction", "deconvolution", "phase"
    requires_gpu: bool = False

    @abstractmethod
    def parameters(self) -> type[BaseModel]:
        """Pydantic model for this plugin's configurable parameters."""
        ...

    @abstractmethod
    def validate(self, acq: Acquisition) -> list[str]:
        """Check if this plugin can process this data. Return warnings."""
        ...

    @abstractmethod
    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        """Process a single frame. Numpy in, numpy out."""
        ...

    def process_region(
        self,
        frames: dict[int, np.ndarray],
        positions: list[FOVPosition],
        params: BaseModel,
    ) -> np.ndarray | None:
        """Override for spatial plugins (stitching). Default: None (not spatial)."""
        return None

    @abstractmethod
    def default_params(self, optical: OpticalMetadata) -> BaseModel:
        """Auto-populate parameters from acquisition metadata."""
        ...

    @abstractmethod
    def test_cases(self) -> list[dict]:
        """Synthetic input/expected output for automated testing."""
        ...
```

Two processing modes:
- `process()`: single-frame plugins (flatfield, decon, background). Takes one array, returns one array.
- `process_region()`: spatial plugins (stitching). Takes all FOV frames + positions, returns fused image. Default returns None (skip for non-spatial plugins).

The pipeline checks which to call. No branching in plugin code.

### Live Processing Behavior Per Algorithm Category

Each algorithm category has its own "live" behavior. The toggle model from v1 is replaced by a richer interaction: the user can select FOVs (drag-box or click), then apply processing to the selection. If nothing is selected, processing runs FOV-by-FOV and the viewer updates as each completes.

The algorithm absorber skill must understand these behaviors when integrating a new repo. Each category defines HOW the algorithm runs live:

**Shading Correction (flatfield, background subtraction)**
- Calibration phase: samples random tiles across the dataset to compute the correction profile (flatfield map, background model). This is a one-time computation, NOT per-tile.
- Application phase: the computed profile is applied as a per-tile transform. Every tile passing through the data pipeline gets corrected.
- Live behavior: user clicks "Calibrate", progress bar fills as random tiles are sampled, then all tiles update simultaneously with the correction applied.
- The correction profile is cached in the sidecar. Recalibrate only if the user requests it.

**Registration / Stitching**
- Pairwise phase: adjacent tile pairs are registered via cross-correlation. The viewer shows pairs being registered live (borders shift as each pair completes). This is progressive and visual.
- Global optimization phase: all pairwise shifts are optimized into globally consistent positions. This happens after pairwise registration completes.
- Fusion phase: overlap zones are blended. This is a render-time operation on visible tiles only.
- Live behavior: user sees tile borders shifting in real-time as registration progresses. Fusion appears in overlap zones. The whole process is visible and interruptible.

**Deconvolution**
- Per-tile iterative operation. Each tile is deconvolved independently (Richardson-Lucy or OMW).
- Live behavior: user selects FOVs (or all), deconvolution runs tile-by-tile, the viewer updates each tile as it completes. The user watches tiles sharpen one by one.
- If nothing selected: starts from the visible viewport, expands outward. The user sees their current view deconvolve first.

**Phase from Defocus**
- Requires a z-stack per FOV. Computes the phase image from the defocus series.
- Live behavior: user selects FOVs, phase retrieval runs per-FOV, viewer updates each FOV with the phase map as it completes.

**Denoising (aCNS)**
- Analytical algorithm. Requires dark frame calibration (100 frames with covered camera).
- Calibration: user provides dark frames (from a calibration acquisition). The noise model is computed once.
- Application: per-tile transform using the noise model.
- Live behavior: same as flatfield. Calibrate once, then all tiles update.

**Cell Segmentation**
- Per-tile or per-region operation. Runs a segmentation model (CellPose, StarDist, etc.) on selected tiles.
- Live behavior: user draws a selection box or clicks tiles. Segmentation runs on selected tiles. Overlays appear (cell boundaries, masks) on each tile as segmentation completes.
- The magical brush: user paints a rough annotation, the model refines it. Interactive, per-tile.

**Cell Tracking**
- Requires time series. Tracks segmented cells across timepoints.
- Live behavior: user selects a cell (click on segmentation overlay), tracking runs forward/backward through time. The viewer shows the track path accumulating across timepoints. Playback animates the track.
- Or: user selects a region, all cells in the region are tracked. Tracks appear progressively.

**Object Detection**
- Per-tile operation. Runs a detection model on selected tiles.
- Live behavior: user selects tiles, detection runs, bounding boxes appear on each tile as detection completes.

**3D Rendering (future, GPU required)**
- User selects FOVs, the z-stack is loaded and rendered as a 3D volume via GPU ray marching.
- Live behavior: user rotates, zooms into the 3D volume. Transfer function adjustable in real-time. Multi-channel composite in 3D via GPU.

### Selection Model

The toggle-only model is insufficient. The full interaction model:

1. **No selection**: processing applies to visible viewport FOVs, expanding outward. The user sees their current view update first.
2. **Drag-box selection**: user drags a rectangle on the stage view. Processing applies only to FOVs intersecting the box.
3. **Click selection**: user clicks individual FOVs. Processing applies to clicked FOVs only.
4. **Select all**: keyboard shortcut (Ctrl+A). Processing applies to entire dataset, FOV-by-FOV from viewport outward.

The selection is decoupled from the algorithm. Any algorithm can run on any selection. The algorithm absorber skill teaches the agent how the algorithm uses the selection.

### Blueprint for Adding a Processing Module

An agent (or developer) follows these steps:

1. Create `processing/{name}/` with `pyproject.toml` and `squid_tools/processing/{name}/plugin.py`
2. Implement `ProcessingPlugin` (5 methods + `process_region` if spatial)
3. Algorithm code goes alongside `plugin.py` in the same package
4. Entry point in `pyproject.toml` makes it discoverable
5. `python -m squid_tools --dev` to test interactively
6. Tests: plugin's `test_cases()` are run automatically by the test harness

---

## Custom Vispy+PySide6 Viewer

No napari. No ndviewer_light. Built on vispy (OpenGL) + PySide6.

### Three files, clear responsibilities

**`canvas.py`**: Talks to the GPU.
- Uploads numpy arrays as OpenGL textures
- Pan/zoom via mouse events and view transform matrix
- Multi-channel compositing: each channel = texture + colormap + blend (GLSL fragment shaders)
- FOV border rendering: line geometry overlay
- Tile placement by pixel coordinates (for mosaic mode)
- Knows nothing about acquisitions, files, dask, or Qt widgets

**`data_manager.py`**: Talks to the data layer.
- Receives viewport bounds from canvas (what region of the mosaic is visible)
- Queries `core/readers` for frames intersecting the viewport
- Uses `core/cache` (memory-bounded LRU) to avoid reloading
- Debounces requests (200ms coalescing, same pattern as ndviewer_light)
- Returns numpy arrays to canvas
- Knows nothing about OpenGL or Qt

**`widget.py`**: Composes into a QWidget.
- Vispy canvas + channel slider + z slider + t slider + FOV selector
- Two modes toggled by button:
  - **Single FOV**: shows one FOV, sliders navigate z/t/channel
  - **Mosaic**: places all region FOVs at (x_mm, y_mm) coordinates, sliders apply to all tiles
- FOV borders: toggle overlay showing tile boundaries (white=nominal, green=registered)
- Double-click FOV in mosaic: jumps to single FOV view of that tile
- Emits signals: `fov_clicked(str, int)`, `view_mode_changed(str)`

### Data flow

```
User pans/zooms
  -> canvas reports viewport bounds
  -> data_manager queries reader for visible tiles
  -> cache hit or reader.read_frame()
  -> numpy array
  -> canvas uploads texture
  -> GPU renders

User clicks "Run Stitch"
  -> controller calls plugin.process_region(frames, positions, params)
  -> stitcher returns fused array
  -> canvas renders fused result as new layer
  -> FOV borders update to registered positions (green)
```

### Memory safety (from ndviewer_light patterns, already in core/)

- Memory-bounded LRU cache (256 MB, evicts by nbytes)
- TiffFile handle pool (128 max, per-file locks)
- Dask lazy loading (zero I/O until viewer requests a slice)
- 200ms debounce on frame loading

---

## Shared Data Model

Unchanged from original spec. Pydantic v2 models parsing Squid's `acquisition.yaml`.

### Squid Output Formats

| Format | Enum | Structure |
|--------|------|-----------|
| OME-TIFF | `OME_TIFF` | `ome_tiff/{region}_{fov:05}.ome.tiff` (TZCYX) |
| Individual images | `INDIVIDUAL_IMAGES` | `{timepoint}/{region}_{fov}_{z}_{channel}.tiff` |
| Zarr | `ZARR` | `plate.ome.zarr/{row}/{col}/{fov}/0` (5D) |

### Metadata sources

| File | Contents |
|------|----------|
| `acquisition.yaml` | Master: objective, z-stack, time series, channels, scan config, regions |
| `coordinates.csv` | Per-timepoint: region, fov, z_level, x/y (mm), z (um), time |
| `acquisition parameters.json` | sensor_pixel_size_um, tube_lens_mm |

### Derived metadata

- `objective.pixel_size_um`: comes from Squid (pre-computed in acquisition.yaml)
- `objective.derived_pixel_size_um`: sensor * binning * (tube_lens_f / mag / tube_lens_mm)
- `optical.*`: user-supplied for decon (modality, immersion, RI, emission wavelength)

---

## GUI Architecture

Thin PySide6 shell. Zero training required. UX informed by:

- **NIS Elements (Nikon)**: right-click context menus for image-specific actions, double-click nested menus for operations on a tile, ribbon-style tab grouping keeps top-level categories visible at all times, visual well plate grid with color coding
- **Araceli Endeavor**: wizard/step-based flows for standard pipelines, minimal training by targeting a linear pipeline metaphor
- **Revvity/Harmony**: linear pipeline builder (drag analysis steps into sequence), well plate grid with heat-map coloring, hover previews, top toolbar for mode switching
- **NIS Elements right-click pattern**: the right control button opens contextual nested dropdowns, making operations simple and discoverable without deep menu nesting

### Color Palette (Cephla brand)

```
Background primary:   #353535  (graphite)
Background secondary: #2a2a2a  (dark graphite)
Text primary:         #ffffff  (white, titles and labels)
Text secondary:       #aaaaaa  (light gray, descriptions)
Text body:            #cccccc  (light gray, content)
Accent:               #2A82DA  (Cephla blue, hover, selection, active states)
Border:               #444444  (dark gray, panel separators)
Disabled:             opacity 0.4 on standard colors
```

The entire GUI uses this palette. No default Qt styling. Custom stylesheet applied globally. Minimal. The Cephla blue is an accent, not a theme. It appears on hover, on selection, on the logo. Everything else is graphite and white. Quiet confidence. The interface should feel like it has nothing to prove.

### Frontend philosophy

Build from scratch. PySide6 (Qt 6) + vispy give full control. The GUI should feel like a polished commercial product, but understated. No gradients, no shadows, no rounded corners for the sake of it. Flat, clean, precise. The data is the centerpiece, not the chrome. If a control isn't needed for the current task, it shouldn't be visible. Complexity reveals itself only when the user asks for it.

### Styling architecture

Three layers produce the commercial feel:

**1. Global QSS stylesheet** applied at app startup. Covers every widget, every state:
```css
QMainWindow { background: #353535; }
QLabel { color: #ffffff; font-family: "Segoe UI", "Helvetica Neue", sans-serif; }
QPushButton { background: #2a2a2a; color: #cccccc; border: 1px solid #444444; padding: 6px 16px; }
QPushButton:hover { border-color: #2A82DA; color: #ffffff; }
QPushButton:pressed { background: #2A82DA; }
QSlider::groove:horizontal { background: #444444; height: 4px; }
QSlider::handle:horizontal { background: #2A82DA; width: 12px; margin: -4px 0; }
QTabBar::tab { background: #2a2a2a; color: #aaaaaa; padding: 8px 20px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #ffffff; border-bottom: 2px solid #2A82DA; }
```

**2. Custom-painted widgets** (QPainter) where QSS is not enough:
- Well plate grid: custom-drawn cells with hover highlight, selection glow, status color fill
- FOV border overlay: rendered by vispy (line geometry in the GL canvas)
- Status indicators: custom-painted dots/badges

**3. Layout precision**: consistent margins (4px inner, 0px between panels), no wasted space, panel separators are 1px #444444 lines. The interface breathes through whitespace in the data area, not through padding in controls.

### Unsupervised agent integration

The architecture must support agents integrating high-quality processing modules without human review for every line. This implies:
- The plugin ABC is the contract. If it passes `validate()` and `test_cases()`, it can ship.
- The test harness runs automatically on any new plugin (CI gate).
- Memory safety checks are automated (no file handles leaked, no unbounded allocations).
- Type checking (mypy strict) catches interface mismatches before runtime.
- ruff enforces code style without human review.
- The integration manual is the agent's instruction set. If the manual is precise enough, the agent produces correct code.

Design principles from these references:
- Dock-widget processing panels with Run buttons (discoverable, extensible)
- Visual well plate grid with color/status coding
- Layer-based results for before/after comparison
- Right-click context menus for situational actions (not buried in menus)
- Double-click on FOV in mosaic opens contextual nested menu (NIS Elements)
- Avoid deep menu nesting to discover features (anti-QuPath)
- Every interactive element has a tooltip
- Human-readable labels everywhere (no code names, no jargon)
- Sensible defaults populated from metadata (user should never need to type a number they don't understand)

### Layout

```
+----------------------------------------------------------+
| [Cephla Logo]  Squid-Tools                      [-][o][x]|
+----------------------------------------------------------+
| [Stitch] [Flatfield]                  Processing Tabs    |
+----------+-------------------------------+---------------+
|          |                               |               |
| Controls |       Viewer                  |  Region       |
|          |                               |  Selector     |
| FOV <->  |  Single FOV  or  Mosaic       |               |
| Mosaic   |  (vispy canvas)               |  [A1][A2]     |
|          |                               |  [B1][B2]     |
| Borders  |  Channel: [====]              |   ...         |
| [show]   |  Z:       [====]              |  or           |
|          |  T:       [====]              |  Region v     |
| Layers   |                               |  dropdown     |
| [toggle] |                               |               |
+----------+-------------------------------+---------------+
| Log: Ready | GPU: CPU only | Mem: 2.1/16 GB             |
+----------------------------------------------------------+
```

### Key interactions

- **Region selector** (right): auto-detects wellplate vs tissue from `acquisition.yaml` `widget_type`. Wellplate shows clickable grid. Tissue shows dropdown.
- **Processing tabs** (top): one tab per installed plugin. Parameter widgets auto-generated from Pydantic model. Run button. Tooltips on everything. Human-readable names (not code names).
- **Controls** (left): FOV/Mosaic toggle, border overlay, layer visibility.
- **Viewer** (center): custom vispy canvas. Single FOV or mosaic. Channel/z/t sliders below canvas.
- **Log panel** (bottom): status, GPU detection, memory usage.
- **File > Open**: QFileDialog for acquisition directory.
- **Double-click FOV in mosaic**: jump to single FOV view.
- **Right-click on viewer**: contextual menu with relevant processing operations.
- **Tooltips on every interactive element.**

### Embeddable mode

`gui/embed.py` exports `SquidToolsWidget(parent)` for Squid's dock layout.

---

## OME Sidecar

Original files never modified. Processing results stored in `.squid-tools/` within the acquisition directory.

```
acquisition_dir/                      # READ-ONLY
├── acquisition.yaml
├── ome_tiff/
└── .squid-tools/                     # Sidecar
    ├── manifest.json                 # Provenance (what ran, when, params)
    └── {plugin_name}/               # Output per plugin
```

Lightweight: manifest is metadata only. Processed frames written only on explicit Save.

---

## Dev Mode

For developers and agents adding new processing modules:

```bash
python -m squid_tools --dev processing/new_module.py
```

1. Hot-loads the .py file via importlib
2. Finds `ProcessingPlugin` subclasses
3. Registers in runtime registry
4. Opens GUI with the plugin available in processing tabs
5. Console shows validation and test_cases() output

The dev mode IS the blueprint. An agent reads the ABC, writes a plugin, tests it in dev mode. No packaging needed until it's ready.

### Integration Manual (for agents and developers)

When absorbing a repo into squid-tools, follow these steps:

**1. Structure:** Keep the source repo's file separation if it's proven. TileFusion has `registration.py`, `fusion.py`, `optimization.py` because those are genuinely separate concerns. Don't flatten what's already modular. Don't split what's naturally one thing.

**2. Strip IO:** Remove all file-reading code from the absorbed repo. The algorithm receives numpy arrays from `core/readers` via the plugin ABC. One read path for the whole system. DRY.

**3. Strip GUI:** Remove any GUI code from the absorbed repo. The algorithm is headless. squid-tools' viewer and processing tabs handle all display.

**4. Plugin wrapper:** Write `plugin.py` implementing `ProcessingPlugin`. This is the only new code. Map the repo's API to the ABC's `process()` / `process_region()` / `parameters()` / `validate()` / `default_params()` / `test_cases()`.

**5. Dependencies:** Declare in the module's own `pyproject.toml`. Only what the algorithm needs. No GUI deps, no reader deps.

**6. Memory safety:** This is the hardest standard. Every absorbed module must:
   - Never hold more than one frame in memory at a time (unless the algorithm requires it, like stitching)
   - Accept and return numpy arrays (not open file handles, not paths)
   - Not allocate GPU memory without the `try: import cupy` pattern
   - Not spawn threads or processes without cleanup

**7. Tests:** The agent writes tests on the spot. Each plugin's `test_cases()` provides synthetic input/output pairs. Integration tests verify the plugin works through the full pipeline (reader -> plugin -> viewer). Test pixel values, not just shapes.

**8. Security:** No `eval()`, no `exec()`, no `subprocess` calls, no network access in processing code. Algorithms are pure functions.

**9. Verify in dev mode:** `python -m squid_tools --dev processing/{name}/plugin.py` loads the plugin, runs test_cases, and opens the GUI with it available.

This manual is the quality gate. An agent that cannot meet these standards should not merge the module.

---

## Distribution

| Target | Format | How |
|--------|--------|-----|
| Windows | `.exe` | PyInstaller bundles selected squid-tools-* packages |
| Linux | `.AppImage` | PyInstaller (same) |
| pip | `pip install` | `pip install squid-tools[stitching,flatfield]` |
| Web page | Downloads | User selects modules, downloads pre-built bundle |

### GPU strategy

- Runtime detection: `try: import cupy` then CPU fallback
- Status bar shows "GPU: {name}" or "GPU: CPU only"
- No build-time CUDA dependency (CuPy wheels include CUDA runtime)

### Web download page (future cycle)

Hosted at a Cloudflare Pages URL (like cephla-downloads.pages.dev). User sees checkboxes for each module, clicks Download, gets a .exe/.AppImage with exactly those modules. No programming knowledge required.

### Development + Demo Network (future cycle)

Three nodes working together:

**1. Dev machine (Mac):** Runs Claude Code with the algorithm absorber skill. Developer points at a repo, the agent absorbs it, writes the plugin, tests it in dev mode on local data. When satisfied, pushes to git.

**2. Cloud (Cloudflare R2 + build server):** Stores test datasets on R2 (S3-compatible, 10 GB free). CI builds .exe/.AppImage bundles for each module combination. New plugin pushes trigger CI to rebuild bundles. The download page auto-updates with new modules.

**3. Web demo (Cloudflare Pages):** Applications scientist demos squid-tools in a browser. The viewer loads data streamed from R2. Users see real microscopy data processed in real-time. No install needed for the demo. When convinced, they download the desktop app.

**The workflow:**
1. Developer says "absorb maragall/Deconvolution"
2. Agent runs the algorithm absorber skill, writes the plugin, tests on local data, pushes to git
3. CI builds a new bundle with deconvolution included, uploads to download page
4. Applications scientist opens the web demo, shows a customer deconvolution on their tissue
5. Customer downloads the bundle with stitching + deconvolution checked
6. Customer opens their data, toggles deconvolution, sees their tissue sharpen

This loop runs continuously. New algorithms are absorbed, tested, built, demoed, and distributed without manual intervention beyond the initial "absorb this repo" command.

---

## v1 Scope (Initial Commit)

### IN

- Namespace package architecture (core, viewer, stitching, flatfield, app)
- Custom vispy+PySide6 continuous zoom viewer (on-demand tile loading, no mode switching)
- Multi-channel additive composite (all fluorescence channels overlaid with per-channel colormap and contrast)
- TileFusion absorbed into processing/stitching (refactored to pure arrays, no own IO)
- Flatfield absorbed into processing/flatfield (BasicPy/scipy)
- Shared data model + 3 format readers (OME-TIFF, Individual, Zarr)
- Memory-safe data flow (LRU cache, handle pool, dask lazy loading, debounce)
- Processing plugin ABC with `process()` and `process_region()`
- AppController wiring GUI to core
- Region/wellplate selector, controls, processing tabs, log panel
- OME sidecar output
- Dev mode for hot-loading plugins
- CLI entry point
- GPU runtime detection
- PyInstaller spec + smoke tests
- ruff + mypy enforcement
- Comprehensive unit + integration tests

### OUT (Future Cycles)

- Background subtraction (sep.Background)
- Deconvolution (PetaKit, absorbed)
- Phase from defocus (waveorder, absorbed)
- aCNS denoising (analytical, dark frame metadata)
- Production logger (Python logging, scrollable panel, log levels, file output)
- Multi-scale pyramid zoom for large mosaics
- 3D volume rendering: extend the continuous zoom viewer to 3D. GPU-accelerated ray marching (vispy VolumeVisual or custom GLSL) for z-stack visualization. The same spatial index and viewport engine apply, but the viewport becomes a 3D frustum. Tiles become 3D chunks. Multi-channel composite moves to GPU (GLSL fragment shader) because CPU ray marching is not viable for real-time 3D. This is when GPU becomes mandatory for the viewer, not optional. The viewer transitions from 2D stage view to 3D stage+z view with a smooth zoom axis.
- MCP API server (high-throughput scripting interface)
- Cell tracking (transfer learning)
- Smart Acquisition (CRUK 3D)
- Formal OME schema validation and standardization
- Media Cybernetics metadata interop
- Web download page for modular bundles
- Checkbox installer UI
- Auto-generated reader classes for new Squid formats
- Navigator integration (downsampled mosaic overview)
- Segmentation / brush / polygon annotation tools
- Web demo: hosted viewer streaming test data so users can try squid-tools in a browser before downloading
- Petabyte-scale optimizations (R-tree spatial index, lazy coordinate parsing, viewport-only contrast) [DONE in v1]
- Async tile loading: background thread loads tiles while GPU renders last frame, eliminating disk I/O stall during pan/zoom
- GPU compositing: move multi-channel additive blend from CPU (numpy) to GPU (CUDA via CuPy). Upload N grayscale textures, composite on device, download RGB result. Target: Linux and Windows with NVIDIA GPUs. CPU fallback for macOS. This eliminates the per-tile compositing cost entirely for users with GPUs, critical for real-time interaction at full resolution with 8+ channels.
- Webapp for module selection: user checks processing modules on a web page, gets a custom bundle
