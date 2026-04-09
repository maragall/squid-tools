# Squid-Tools Design Spec

## Purpose

Squid-tools is the open-source post-processing companion for Cephla-Lab/Squid. It is a **connector** that wraps well-known microscopy algorithms into a unified, data-intensive system that reads Squid's acquisition formats and provides both a visual GUI and a scriptable API.

**Audience:** Life sciences researchers on Windows and Linux workstations. They do not know how to configure GPUs. The software must work out of the box.

**Guiding principle:** Thin PyQt5 GUI shell over a data-intensive core library with zero GUI dependencies. The same core serves both interactive viewing and high-throughput batch processing.

---

## Architecture: Core Library + Thin Shell (Option B)

```
squid-tools/
├── core/                        # Zero GUI dependencies
│   ├── data_model.py            # Pydantic v2 models, metadata parsing
│   ├── acquisition.py           # 5D lazy array interface (dask-backed)
│   ├── readers/                 # Format readers (ABC pattern)
│   │   ├── base.py              # FormatReader ABC
│   │   ├── ome_tiff.py          # OME-TIFF reader
│   │   ├── individual.py        # Individual images reader
│   │   └── zarr_reader.py       # Zarr v3 reader (HCS + non-HCS)
│   ├── pipeline.py              # Processing pipeline (chain operations)
│   ├── sidecar.py               # Non-destructive output
│   └── registry.py              # Plugin discovery + registration
├── plugins/                     # Each wraps an existing repo
│   ├── base.py                  # ProcessingPlugin ABC
│   ├── stitcher.py              # Wraps TileFusion (maragall/stitcher)
│   ├── decon.py                 # Wraps PetaKit (maragall/Deconvolution)
│   ├── background.py            # Wraps sep.Background
│   └── flatfield.py             # Wraps BasicPy (within stitcher)
├── gui/                         # Thin PyQt5 shell, imports core/
│   ├── app.py                   # Standalone entry point
│   ├── viewer.py                # Single FOV viewer (wraps ndviewer_light)
│   ├── mosaic.py                # Mosaic view (napari + dask tiling)
│   ├── wellplate.py             # Well plate / region selector widget
│   ├── processing_panel.py      # Dock-widget panels per plugin
│   └── embed.py                 # Embeddable widget for Squid
├── api/                         # High-throughput scripting (cycle 2)
│   └── server.py                # MCP-compatible JSON API
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── conftest.py
└── installer/
    ├── entry.py                 # Frozen exe entry point
    └── squid_tools.spec         # PyInstaller spec
```

---

## Shared Data Model

The data model is the spine. Every module reads through it. It parses Squid's output directory and provides a uniform interface to all plugins and the GUI.

### Squid Output Formats

| Format | Enum | Structure |
|--------|------|-----------|
| OME-TIFF | `OME_TIFF` | `ome_tiff/{region}_{fov:05}.ome.tiff`: TZCYX axis order, OME-XML header |
| Individual images | `INDIVIDUAL_IMAGES` | `{timepoint}/{region}_{fov:05}_C{ch:02}.tiff`: one file per frame |
| Zarr | `ZARR` | HCS: `plate.ome.zarr/{row}/{col}/{fov}/0` (5D) or non-HCS: `zarr/{region}/fov_{n}.ome.zarr` |

Multi-page TIFF is discontinued.

### Metadata Sources

| File | Contents | When Present |
|------|----------|--------------|
| `acquisition.yaml` | Master file: objective, z-stack, time series, channels, scan config, wellplate/flexible params | Always |
| `coordinates.csv` | Per-timepoint: region, fov, z_level, x/y (mm), z (um), time, z_piezo (um) | Always |
| `acquisition parameters.json` | sensor_pixel_size_um, tube_lens_mm, confocal_mode, channel configs | Always |
| `acquisition_channels.yaml` | Channel configuration (illumination, camera settings) | When configured |
| OME-XML (in TIFF header) | Physical sizes, channel names, per-plane positions | OME-TIFF format |
| TIFF ImageDescription JSON | z_level, channel, region_id, fov, position | Individual images format |

### Core Models (Pydantic v2)

```python
class AcquisitionFormat(str, Enum):
    OME_TIFF = "OME_TIFF"
    INDIVIDUAL_IMAGES = "INDIVIDUAL_IMAGES"
    ZARR = "ZARR"

class AcquisitionMode(str, Enum):
    WELLPLATE = "wellplate"
    FLEXIBLE = "flexible"
    MANUAL = "manual"

class ObjectiveMetadata(BaseModel):
    name: str
    magnification: float
    numerical_aperture: float
    tube_lens_f_mm: float
    sensor_pixel_size_um: float
    camera_binning: int = 1
    tube_lens_mm: float

    @computed_field
    @property
    def pixel_size_um(self) -> float:
        """dxy at sample plane. Matches Squid ObjectiveStore calculation."""
        lens_factor = self.tube_lens_f_mm / self.magnification / self.tube_lens_mm
        return self.sensor_pixel_size_um * self.camera_binning * lens_factor

class OpticalMetadata(BaseModel):
    modality: Literal["widefield", "confocal", "two_photon", "lightsheet", "spinning_disk"]
    immersion_medium: Literal["air", "water", "oil", "glycerol", "silicone"]
    immersion_ri: float
    numerical_aperture: float
    pixel_size_um: float
    dz_um: float | None = None

class AcquisitionChannel(BaseModel):
    name: str
    illumination_source: str
    illumination_intensity: float
    exposure_time_ms: float
    emission_wavelength_nm: float | None = None
    z_offset_um: float = 0.0

class ScanConfig(BaseModel):
    acquisition_pattern: Literal["S-Pattern", "Unidirectional"]
    fov_pattern: Literal["S-Pattern", "Unidirectional"]
    overlap_percent: float | None = None

class GridParams(BaseModel):
    scan_size_mm: float
    overlap_percent: float
    nx: int
    ny: int

class FrameKey(NamedTuple):
    """Uniquely identifies a single 2D frame in an acquisition."""
    region: str
    fov: int
    z: int
    channel: int
    timepoint: int

class FOVPosition(BaseModel):
    fov_index: int
    x_mm: float
    y_mm: float
    z_um: float | None = None
    z_piezo_um: float | None = None

class Region(BaseModel):
    region_id: str                                    # "A1", "manual0", etc.
    center_mm: tuple[float, float, float]
    shape: Literal["Square", "Rectangle", "Circle", "Manual"]
    fovs: list[FOVPosition]
    grid_params: GridParams | None = None             # overlap, scan_size if grid

class ZStackConfig(BaseModel):
    nz: int
    delta_z_mm: float
    direction: Literal["FROM_BOTTOM", "FROM_TOP"]
    use_piezo: bool = False

class TimeSeriesConfig(BaseModel):
    nt: int
    delta_t_s: float

class Acquisition(BaseModel):
    """Top-level entry point. One per dataset.
    Parsed primarily from acquisition.yaml."""
    path: Path
    format: AcquisitionFormat
    mode: AcquisitionMode
    objective: ObjectiveMetadata
    optical: OpticalMetadata
    channels: list[AcquisitionChannel]
    scan: ScanConfig
    z_stack: ZStackConfig | None = None
    time_series: TimeSeriesConfig | None = None
    regions: dict[str, Region]

    def frames(self, region=None, fov=None, z=None, ch=None, t=None) -> dask.array:
        """Lazy 5D array access (TZCYX). Only materializes on slice request."""
        ...
```

### Format Readers (ABC Pattern from image-stitcher)

```python
class FormatReader(ABC):
    @classmethod
    @abstractmethod
    def detect(cls, path: Path) -> bool:
        """Can this reader handle the given acquisition directory?"""
        ...

    @abstractmethod
    def read_metadata(self, path: Path) -> Acquisition:
        """Parse all metadata into the unified Acquisition model."""
        ...

    @abstractmethod
    def read_frame(self, key: FrameKey) -> np.ndarray:
        """Load a single frame by (region, fov, z, channel, timepoint)."""
        ...

class OMETiffReader(FormatReader): ...
class IndividualImageReader(FormatReader): ...
class ZarrReader(FormatReader): ...
```

### Derived Metadata

Plugins should never recompute physical parameters. All derived values live on the models:

- `objective.pixel_size_um`: dxy at sample plane (sensor × binning × lens_factor)
- `optical.dz_um`: z-step from z_stack config
- `optical.immersion_ri`: defaulted per medium (water=1.333, oil=1.515, etc.)
- Channel emission/excitation wavelengths from `AcquisitionChannel`

---

## Memory-Safe Data Flow

Patterns lifted directly from ndviewer_light (proven in production):

### Memory-Bounded LRU Cache
- Evicts by `nbytes`, not item count: bounds actual RAM usage
- Rejects single items larger than max (256 MB default) to prevent cache deadlock
- `OrderedDict.move_to_end()` on hit: O(1) recency update
- Thread-safe via `threading.Lock()` on all cache operations

### TiffFile Handle Pool
- 128-handle LRU cap prevents file descriptor exhaustion
- Per-file locks enable parallel reads across files while serializing same-file reads
- Evicted handles closed outside the global lock to prevent contention

### Dask Lazy Loading
- `dask.delayed()` wraps every frame read: zero I/O until the viewer or pipeline requests a slice
- 5D array structure (T, Z, C, Y, X) built from delayed tasks with shape/dtype metadata only
- Only viewport-visible frames materialize

### Debounce
- 200ms QTimer coalescing for rapid frame updates
- `_load_pending` flag prevents UI thread flood during live acquisition
- `was_written_before_read` flag prevents caching stale data during streaming

### Data Flow

```
FormatReader.read_frame()
    → TiffFile Handle Pool (128 max, per-file locks)
    → dask.delayed(): zero I/O until slice requested
    → MemoryBoundedLRUCache (256 MB, nbytes-aware eviction)
    → Plugin.process(): lazy in, lazy out
    → GUI: debounced napari layer update
      API: batch materialization to sidecar
```

---

## Plugin Interface (the "Carpenter's Table")

Every processing module implements one class. Wrapping a new algorithm = one file, ~50 lines.

```python
class ProcessingPlugin(ABC):
    name: str
    category: str       # "stitching" | "deconvolution" | "correction" | "phase"
    requires_gpu: bool = False

    @abstractmethod
    def parameters(self) -> type[BaseModel]:
        """Pydantic model defining this plugin's configurable parameters."""
        ...

    @abstractmethod
    def validate(self, acq: Acquisition) -> list[str]:
        """Check if this plugin can run on this data. Return warnings/errors."""
        ...

    @abstractmethod
    def process(self, frames: dask.array, params: BaseModel) -> dask.array:
        """Transform frames. Lazy dask in, lazy dask out."""
        ...

    @classmethod
    def default_params(cls, optical: OpticalMetadata) -> BaseModel:
        """Auto-populate parameters from acquisition metadata."""
        ...

    @abstractmethod
    def test_cases(self) -> list[TestCase]:
        """Synthetic input/expected output pairs for unit tests.
        Context delegated to the LLM developing this plugin."""
        ...
```

### Cycle 1 Plugins

| Plugin | Wraps | GPU | What It Does |
|--------|-------|-----|-------------|
| `StitcherPlugin` | TileFusion (maragall/stitcher) | CuPy optional | Tile registration + fusion, OME-TIFF export |
| `DeconPlugin` | PetaKit (maragall/Deconvolution) | CuPy (CPU fallback) | Richardson-Lucy / OMW deconvolution |
| `BackgroundPlugin` | sep.Background | No | Background subtraction |
| `FlatfieldPlugin` | BasicPy (in stitcher) | No | Flatfield illumination correction |

### Plugin Discovery

Via Python entry points: each checked module at install time registers itself:

```toml
[project.entry-points."squid_tools.plugins"]
stitcher = "squid_tools.plugins.stitcher:StitcherPlugin"
decon = "squid_tools.plugins.decon:DeconPlugin"
background = "squid_tools.plugins.background:BackgroundPlugin"
flatfield = "squid_tools.plugins.flatfield:FlatfieldPlugin"
```

---

## OME Sidecar

Processing results are stored alongside the acquisition in a standardized OME-compatible sidecar structure. Original files are never modified. This follows the OME companion file pattern, where processed outputs and provenance metadata live in a separate directory that any OME-aware tool can discover:

```
acquisition_2024_01_15/                  # Squid's output (READ-ONLY)
├── acquisition.yaml
├── coordinates.csv
├── ome_tiff/
└── .squid-tools/                        # Sidecar directory
    ├── manifest.json                    # Processing provenance
    └── {plugin_name}/                   # Per-plugin output
        └── {output files}
```

### manifest.json

Pydantic model tracking what was run, when, with what parameters:

```json
{
  "runs": [
    {
      "plugin": "TileFusion Stitcher",
      "version": "0.3.1",
      "timestamp": "2026-04-07T14:30:00Z",
      "params": {"overlap_percent": 15, "registration": true},
      "input_hash": "sha256:...",
      "output_path": "stitcher/"
    }
  ]
}
```

### Memory Footprint

The sidecar must not significantly increase storage:
- `manifest.json` is metadata only (bytes)
- Processed frames written only on explicit user "Save" action
- No duplication of raw data: lazy references until materialized
- Pipeline state (which transforms were applied, with what params) stored in manifest, not as copied data

---

## Mosaic Rendering

Uses **napari + dask.array + tifffile**: the proven microscopy tiling stack. No custom rendering engine.

### How It Works

1. Each FOV is a `dask.delayed` tile placed at its `(x_mm, y_mm)` coordinates via napari `translate` transforms
2. napari handles viewport-based rendering: only visible tiles are materialized
3. Zoom out: napari's multiscale support shows lower-resolution versions
4. Pan: adjacent tiles loaded on demand from the dask/cache pipeline
5. For very large mosaics (hundreds/thousands of FOVs): Google Maps-style: assemble visible center NxM tiles, load more as user pans/zooms

### FOV Border Overlay

- napari `Shapes` layer with rectangles at each FOV position
- Color-coded: white = nominal (stage coordinates), green = registered, red = failed
- Overlap/intersection regions shown as semi-transparent shapes
- When registration runs and completes (Option B): shapes layer updates with new positions, user toggles layers to compare before/after

### Single FOV ↔ Mosaic Toggle

- Button toggles between single FOV view (ndviewer_light: full 5D navigation) and mosaic view (napari tiled assembly)
- In mosaic: double-click an FOV to jump to single FOV view of that tile
- In single FOV: button returns to mosaic at the same region

---

## GUI Architecture

Thin PyQt5 shell. Informed by NIS Elements (right-click + double-click nested menus, well plate grid), Napari (dock-widget panels, layer-based results), and Harmony (linear pipeline). Avoids QuPath's deep menu nesting.

### Layout

```
┌──────────────────────────────────────────────────────────┐
│ [Cephla Logo]  Squid-Tools                      [─][□][×]│
├──────────────────────────────────────────────────────────┤
│ [Stitch] [Decon] [BgSub] [Flatfield]   Processing Tabs  │
├──────────┬───────────────────────────────┬───────────────┤
│          │                               │               │
│ Controls │       Viewer Panel            │  Region       │
│          │                               │  Selector     │
│ FOV ↔    │  ┌────────┐  ┌──────────┐    │               │
│ Mosaic   │  │Single  │⇄│ Mosaic   │    │  [A1][A2]     │
│          │  │FOV View│  │ View     │    │  [B1][B2]     │
│ Borders  │  └────────┘  └──────────┘    │   ...         │
│ [show]   │                               │  ────────     │
│          │  Layers:                      │  or           │
│ Layers   │  [original] [processed]       │  Region ▾     │
│ [toggle] │                               │  dropdown     │
│          │                               │               │
├──────────┴───────────────────────────────┴───────────────┤
│ Log: Ready | GPU: NVIDIA RTX 3080 | Mem: 2.1/16 GB      │
└──────────────────────────────────────────────────────────┘
```

The region selector auto-detects wellplate vs tissue from `acquisition.yaml` `widget_type` field. Wellplate mode shows a clickable grid. Tissue/flexible mode shows a region dropdown or list.

### Key Interactions

- **Region selector** (right panel): Auto-detects wellplate vs tissue from `acquisition.yaml` `widget_type` field. Wellplate shows clickable grid (adapted from Squid's `ScanCoordinates`). Tissue/flexible shows region dropdown. Click region to load its FOVs.
- **Processing tabs** (top): One tab per installed plugin. Each tab shows parameter widgets (auto-generated from plugin's Pydantic model) and a Run button. Click Run, result appears as new napari layer.
- **Controls** (left panel): FOV/Mosaic toggle, border overlay show/hide, layer visibility toggles.
- **Double-click nested menus**: Double-click on FOV in mosaic opens contextual nested menu with relevant operations (NIS Elements pattern).
- **Layer-based results**: Each processing result is a new layer. Toggle visibility for before/after comparison.
- **Tooltips**: On every button, every parameter, every tab header.
- **Right-click context menus**: Right-click on viewer for operations relevant to the current selection.
- **Log panel** (bottom): Status, GPU detection, memory usage, processing progress, errors.

### Embeddable Mode

`gui/embed.py` exports `SquidToolsWidget(parent)` that Squid can embed in its dock layout, identical to the current NDViewerTab integration pattern. Uses Qt signals for thread-safe communication with Squid's acquisition controller.

---

## Testing Strategy

### Tools

- **ruff**: formatting + linting (from image-stitcher patterns)
- **mypy**: full type checking
- **pytest**: unit + integration tests

### Test Structure

```
tests/
├── unit/                        # Fast, no GPU, no disk I/O
│   ├── test_data_model.py       # Pydantic validation, serialization, computed fields
│   ├── test_readers.py          # Format detection, metadata parsing (fixture data)
│   ├── test_pipeline.py         # Plugin chaining, lazy evaluation correctness
│   ├── test_sidecar.py          # Manifest read/write, provenance tracking
│   └── test_pixel_size.py       # Derived metadata math (dxy calculation)
├── integration/                 # Needs disk, optional GPU
│   ├── test_stitcher.py         # TileFusion end-to-end with synthetic tiles
│   ├── test_decon.py            # PetaKit with synthetic PSF
│   ├── test_background.py       # sep.Background on synthetic data
│   ├── test_flatfield.py        # BasicPy correction validation
│   ├── test_viewer.py           # GUI smoke test (xvfb on CI)
│   └── test_mosaic.py           # Mosaic assembly from coordinates
├── fixtures/
│   └── generate_fixtures.py     # Creates synthetic Squid acquisitions (all 3 formats)
└── conftest.py                  # Shared fixtures, @pytest.mark.gpu skip markers
```

### Plugin Test Contract

Each plugin implements `test_cases()` returning synthetic input/expected output pairs. The test runner validates all registered plugins automatically. Test context is delegated to the LLM developing each plugin: the ABC enforces the contract.

### Fixture Generator

Creates realistic multi-FOV Squid acquisitions programmatically:
- All 3 formats (OME_TIFF, INDIVIDUAL_IMAGES, ZARR)
- With valid `acquisition.yaml`, `coordinates.csv`, `acquisition parameters.json`
- Configurable: grid size, channels, z-levels, timepoints
- Follows image-stitcher's `temporary_image_directory_params()` pattern

---

## Dev Mode

Plugin development workflow for rapid iteration:

```
squid-tools --dev                    # launches GUI with dev panel
squid-tools --dev my_plugin.py       # hot-loads a plugin file
```

Dev panel features:
- Load any plugin file (no install needed, just a .py implementing `ProcessingPlugin`)
- Pick test data: local directory or stream from Zenodo test data registry
- Run plugin on data, see result as napari layer
- Validate against `test_cases()` output
- Parameter widget preview (auto-generated from Pydantic model)
- Console dock panel for logs/errors

A plugin developer's workflow: write the class, point dev mode at it, see results on real data. No packaging until ready.

---

## Test Data (Zenodo + pooch)

Test data is hosted on Zenodo (free, 50 GB, permanent DOI), not in the git repo. The `pooch` library downloads and caches datasets on first use.

### Zenodo Dataset Organization

Each upload is a zip containing a complete Squid acquisition directory:

```
ome_tiff_wellplate_3x3.zip          # OME-TIFF, wellplate, 3x3 grid per well
ome_tiff_tissue_manual.zip          # OME-TIFF, tissue, manual regions
individual_wellplate_3x3.zip        # Individual images, wellplate
individual_tissue_manual.zip        # Individual images, tissue
zarr_hcs_wellplate_96.zip           # Zarr HCS, 96-well plate
zarr_non_hcs_tissue.zip             # Zarr non-HCS, tissue
```

Each zip contains:
```
{name}/
├── acquisition.yaml
├── coordinates.csv
├── acquisition parameters.json
└── {format-specific data files}
```

### Usage

```python
from squid_tools.core.test_data import fetch
path = fetch("ome_tiff_wellplate_3x3.zip")  # downloads once, caches in ~/.cache/squid-tools/
acq = Acquisition.from_path(Path(path))
```

### Setup Steps

1. Go to https://zenodo.org/deposit/new
2. Create a new deposit for "squid-tools-test-data"
3. Upload the zip files following the naming convention above
4. Publish and copy the record DOI
5. Update `ZENODO_DOI` and `ZENODO_RECORD` in `core/test_data.py`
6. Update SHA256 hashes in the registry dict

### Limitations

Zenodo + pooch downloads full files (no remote streaming). For unit and integration tests this is the right approach: download once, cache, test on local files. This is the same pattern used by scikit-image, scipy, and napari.

If remote Zarr streaming is needed later (demos, dev mode), Cloudflare R2 (10 GB free, S3-compatible) can be added without changing the test infrastructure.

---

## Distribution

| Target | Format | How |
|--------|--------|-----|
| Windows | `.exe` | PyInstaller (follows ndviewer_light + PetaKit build patterns) |
| Linux | `.AppImage` | PyInstaller (follows PetaKit pattern) |
| Squid embed | `pip install` | `pip install squid-tools` or `pip install squid-tools[gpu]` |

### GPU Strategy for Life Scientists

- **Runtime detection**: `try: import cupy` → CPU fallback with status bar message "GPU not detected, running on CPU"
- **No build-time CUDA dependency**: CuPy wheels include CUDA runtime
- **Installer checkbox**: "Install GPU support (requires NVIDIA GPU)" with tooltip
- CuPy/PyTorch optional deps in `[gpu]` extras

---

## Cycle 1 Scope: Fully Functional End-to-End

### IN

- Shared data model (OME_TIFF + INDIVIDUAL_IMAGES + ZARR readers)
- Plugin ABC + wrappers: TileFusion, PetaKit, sep.Background, BasicPy
- PyQt5 shell: well plate selector, single FOV viewer (ndviewer_light), mosaic view (napari), processing dock panels with all 4 plugins
- FOV border overlay with intersection/overlap visualization
- Single FOV ↔ mosaic instant toggle
- Live transform application (Option B: click Run, result as new layer)
- OME sidecar output
- Embeddable widget mode for Squid
- Unit tests for data model + each plugin + derived metadata
- Integration tests with synthetic Squid acquisitions
- Windows .exe build, Linux .AppImage build
- Cephla logo
- ruff + mypy enforcement

### OUT (Future Cycles)

- MCP API server (high-throughput scripting interface)
- Formal OME schema validation and standardization
- Phase from defocus plugin
- aCNS denoising plugin (analytical, needs dark frame metadata)
- Segmentation / brush / polygon annotation tools
- Cell tracking (transfer learning)
- Smart Acquisition (CRUK 3D)
- Navigator integration (downsampled mosaic overview)
- Auto-generated reader classes for new Squid formats
- Media Cybernetics metadata interop
