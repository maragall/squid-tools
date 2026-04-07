# Squid-Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the squid-tools connector: a data-intensive microscopy post-processing system with a thin PyQt5 GUI, plugin architecture, and shared data model for Squid's acquisition formats.

**Architecture:** Core library (zero GUI deps) with Pydantic v2 data models, dask-backed lazy loading, and a ProcessingPlugin ABC. Thin PyQt5 shell with napari-based mosaic rendering. Embeddable in Squid. Distributed as .exe (Windows) and .AppImage (Linux).

**Tech Stack:** Python 3.10+, Pydantic v2, dask, tifffile, zarr, napari, PyQt5, vispy, pooch, ruff, mypy, pytest, PyInstaller

**Spec:** `docs/superpowers/specs/2026-04-07-squid-tools-design.md`

**Reference repos (cloned to `_audit/`):**
- `_audit/Squid` : Squid acquisition system (metadata formats, GUI patterns, MCP server)
- `_audit/image-stitcher` : Gold-standard patterns (Pydantic, ABC, ruff/mypy, testing)
- `_audit/ndviewer_light` : Viewer core (memory safety, LRU cache, dask loading, PyInstaller)
- `_audit/stitcher` : TileFusion stitching (GPU/CPU registration)
- `_audit/Deconvolution` : PetaKit deconvolution (CuPy GPU)
- `_audit/phase_from_defocus` : Phase retrieval (waveorder)
- `_audit/ndviewer` : Old viewer (navigator concepts)

---

## File Structure

```
squid_tools/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── data_model.py            # Pydantic v2 models (all enums, metadata, Acquisition)
│   ├── readers/
│   │   ├── __init__.py
│   │   ├── base.py              # FormatReader ABC
│   │   ├── ome_tiff.py          # OME-TIFF reader
│   │   ├── individual.py        # Individual images reader
│   │   ├── zarr_reader.py       # Zarr v3 reader
│   │   └── detect.py            # Auto-detection: path -> reader
│   ├── cache.py                 # MemoryBoundedLRUCache
│   ├── handle_pool.py           # TiffFile handle pool (128 max, per-file locks)
│   ├── acquisition.py           # Lazy 5D array construction (dask)
│   ├── pipeline.py              # Processing pipeline (chain plugins)
│   ├── sidecar.py               # OME sidecar (manifest + output)
│   ├── registry.py              # Plugin discovery via entry_points
│   └── test_data.py             # Zenodo + pooch test data fetcher
├── plugins/
│   ├── __init__.py
│   ├── base.py                  # ProcessingPlugin ABC + TestCase model
│   ├── stitcher.py              # Wraps TileFusion
│   ├── decon.py                 # Wraps PetaKit
│   ├── background.py            # Wraps sep.Background
│   └── flatfield.py             # Wraps BasicPy
├── gui/
│   ├── __init__.py
│   ├── app.py                   # MainWindow + standalone entry point
│   ├── viewer.py                # Single FOV viewer (wraps ndviewer_light)
│   ├── mosaic.py                # Mosaic view (napari tiled)
│   ├── wellplate.py             # Well plate grid / region selector (right panel)
│   ├── controls.py              # Left panel (FOV/mosaic toggle, borders, layers)
│   ├── processing_tabs.py       # Top tab bar with plugin panels
│   ├── log_panel.py             # Bottom log/status panel
│   ├── borders.py               # FOV border overlay (napari Shapes layer)
│   └── embed.py                 # Embeddable widget for Squid
├── dev/
│   └── dev_panel.py             # Dev mode panel (hot-load plugins)
tests/
├── conftest.py                  # Shared fixtures, GPU skip markers
├── unit/
│   ├── test_data_model.py
│   ├── test_pixel_size.py
│   ├── test_cache.py
│   ├── test_handle_pool.py
│   ├── test_readers.py
│   ├── test_pipeline.py
│   ├── test_sidecar.py
│   └── test_registry.py
├── integration/
│   ├── test_stitcher.py
│   ├── test_decon.py
│   ├── test_background.py
│   ├── test_flatfield.py
│   └── test_mosaic.py
└── fixtures/
    └── generate_fixtures.py     # Synthetic Squid acquisition generator
pyproject.toml
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `squid_tools/__init__.py`
- Create: `squid_tools/core/__init__.py`
- Create: `squid_tools/plugins/__init__.py`
- Create: `squid_tools/gui/__init__.py`
- Create: `squid_tools/dev/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/fixtures/__init__.py`
- Create: `.gitignore`
- Move: `core/test_data.py` to `squid_tools/core/test_data.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "squid-tools"
version = "0.1.0"
description = "Post-processing connector for Cephla-Lab Squid microscopy"
requires-python = ">=3.10"
dependencies = [
    "pydantic>=2.10",
    "numpy>=1.24",
    "dask[array]>=2024.1",
    "tifffile>=2024.1",
    "zarr>=2.16",
    "scipy>=1.11",
    "pooch>=1.8",
    "PyYAML>=6.0",
]

[project.optional-dependencies]
gui = [
    "PyQt5>=5.15",
    "napari>=0.4.19",
    "ndv>=0.4.0,<0.5.0",
    "vispy>=0.14",
    "superqt>=0.6",
]
gpu = [
    "cupy-cuda12x>=13.0",
]
dev = [
    "pytest>=8.0",
    "ruff>=0.4",
    "mypy>=1.10",
]

[project.entry-points."squid_tools.plugins"]
stitcher = "squid_tools.plugins.stitcher:StitcherPlugin"
decon = "squid_tools.plugins.decon:DeconPlugin"
background = "squid_tools.plugins.background:BackgroundPlugin"
flatfield = "squid_tools.plugins.flatfield:FlatfieldPlugin"

[project.scripts]
squid-tools = "squid_tools.gui.app:main"

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.10"
strict = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "gpu: requires NVIDIA GPU with CUDA",
]
```

- [ ] **Step 2: Create package init files**

Create empty `__init__.py` in each directory:
- `squid_tools/__init__.py`
- `squid_tools/core/__init__.py`
- `squid_tools/core/readers/__init__.py`
- `squid_tools/plugins/__init__.py`
- `squid_tools/gui/__init__.py`
- `squid_tools/dev/__init__.py`
- `tests/__init__.py`
- `tests/unit/__init__.py`
- `tests/integration/__init__.py`
- `tests/fixtures/__init__.py`

- [ ] **Step 3: Create .gitignore**

```gitignore
__pycache__/
*.pyc
*.egg-info/
dist/
build/
.mypy_cache/
.ruff_cache/
.pytest_cache/
_audit/
*.DS_Store
```

- [ ] **Step 4: Move test_data.py to correct location**

Move `core/test_data.py` to `squid_tools/core/test_data.py`. Delete the old `core/` directory.

- [ ] **Step 5: Verify scaffolding**

Run: `pip install -e ".[dev]" && python -c "import squid_tools; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Verify ruff and mypy**

Run: `ruff check squid_tools/ && echo "ruff ok"`
Run: `mypy squid_tools/ && echo "mypy ok"`
Expected: both pass (empty package)

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: scaffold squid-tools package with pyproject.toml, ruff, mypy"
```

---

## Task 2: Pydantic Data Models

**Files:**
- Create: `squid_tools/core/data_model.py`
- Create: `tests/unit/test_data_model.py`
- Create: `tests/unit/test_pixel_size.py`

- [ ] **Step 1: Write failing tests for enums and basic models**

```python
# tests/unit/test_data_model.py
from squid_tools.core.data_model import (
    AcquisitionFormat,
    AcquisitionMode,
    ObjectiveMetadata,
    OpticalMetadata,
    AcquisitionChannel,
    ScanConfig,
    GridParams,
    FrameKey,
    FOVPosition,
    Region,
    ZStackConfig,
    TimeSeriesConfig,
    Acquisition,
)


def test_acquisition_format_enum():
    assert AcquisitionFormat.OME_TIFF == "OME_TIFF"
    assert AcquisitionFormat.INDIVIDUAL_IMAGES == "INDIVIDUAL_IMAGES"
    assert AcquisitionFormat.ZARR == "ZARR"


def test_acquisition_mode_enum():
    assert AcquisitionMode.WELLPLATE == "wellplate"
    assert AcquisitionMode.FLEXIBLE == "flexible"
    assert AcquisitionMode.MANUAL == "manual"


def test_objective_metadata_validation():
    obj = ObjectiveMetadata(
        name="20x",
        magnification=20.0,
        numerical_aperture=0.75,
        tube_lens_f_mm=200.0,
        sensor_pixel_size_um=3.45,
        camera_binning=1,
        tube_lens_mm=200.0,
    )
    assert obj.name == "20x"
    assert obj.magnification == 20.0


def test_optical_metadata_immersion_defaults():
    opt = OpticalMetadata(
        modality="widefield",
        immersion_medium="water",
        immersion_ri=1.333,
        numerical_aperture=0.75,
        pixel_size_um=0.1725,
    )
    assert opt.immersion_ri == 1.333
    assert opt.dz_um is None


def test_acquisition_channel():
    ch = AcquisitionChannel(
        name="DAPI",
        illumination_source="LED_405",
        illumination_intensity=50.0,
        exposure_time_ms=100.0,
        emission_wavelength_nm=461.0,
    )
    assert ch.z_offset_um == 0.0


def test_scan_config():
    sc = ScanConfig(
        acquisition_pattern="S-Pattern",
        fov_pattern="Unidirectional",
        overlap_percent=15.0,
    )
    assert sc.acquisition_pattern == "S-Pattern"


def test_frame_key():
    fk = FrameKey(region="A1", fov=0, z=3, channel=1, timepoint=0)
    assert fk.region == "A1"
    assert fk.fov == 0


def test_fov_position():
    fov = FOVPosition(fov_index=0, x_mm=1.5, y_mm=2.3)
    assert fov.z_um is None
    assert fov.z_piezo_um is None


def test_region():
    region = Region(
        region_id="A1",
        center_mm=(10.0, 20.0, 0.0),
        shape="Square",
        fovs=[FOVPosition(fov_index=0, x_mm=9.5, y_mm=19.5)],
        grid_params=GridParams(scan_size_mm=2.0, overlap_percent=15.0, nx=3, ny=3),
    )
    assert len(region.fovs) == 1
    assert region.grid_params is not None


def test_zstack_config():
    zs = ZStackConfig(nz=10, delta_z_mm=0.001, direction="FROM_BOTTOM")
    assert zs.use_piezo is False


def test_timeseries_config():
    ts = TimeSeriesConfig(nt=100, delta_t_s=30.0)
    assert ts.nt == 100


def test_acquisition_json_roundtrip():
    acq = Acquisition(
        path="/tmp/test",
        format=AcquisitionFormat.OME_TIFF,
        mode=AcquisitionMode.WELLPLATE,
        objective=ObjectiveMetadata(
            name="20x",
            magnification=20.0,
            numerical_aperture=0.75,
            tube_lens_f_mm=200.0,
            sensor_pixel_size_um=3.45,
            camera_binning=1,
            tube_lens_mm=200.0,
        ),
        optical=OpticalMetadata(
            modality="widefield",
            immersion_medium="air",
            immersion_ri=1.0,
            numerical_aperture=0.75,
            pixel_size_um=0.1725,
        ),
        channels=[
            AcquisitionChannel(
                name="DAPI",
                illumination_source="LED_405",
                illumination_intensity=50.0,
                exposure_time_ms=100.0,
            )
        ],
        scan=ScanConfig(
            acquisition_pattern="S-Pattern",
            fov_pattern="Unidirectional",
        ),
        regions={
            "A1": Region(
                region_id="A1",
                center_mm=(10.0, 20.0, 0.0),
                shape="Square",
                fovs=[FOVPosition(fov_index=0, x_mm=9.5, y_mm=19.5)],
            )
        },
    )
    json_str = acq.model_dump_json()
    restored = Acquisition.model_validate_json(json_str)
    assert restored.format == AcquisitionFormat.OME_TIFF
    assert restored.regions["A1"].region_id == "A1"
```

- [ ] **Step 2: Write failing pixel size tests**

```python
# tests/unit/test_pixel_size.py
from squid_tools.core.data_model import ObjectiveMetadata


def test_pixel_size_20x_standard():
    """20x objective, 200mm tube lens, 3.45um sensor, no binning.
    dxy = 3.45 * 1 * (200 / 20 / 200) = 3.45 * 0.05 = 0.1725 um"""
    obj = ObjectiveMetadata(
        name="20x",
        magnification=20.0,
        numerical_aperture=0.75,
        tube_lens_f_mm=200.0,
        sensor_pixel_size_um=3.45,
        camera_binning=1,
        tube_lens_mm=200.0,
    )
    assert abs(obj.pixel_size_um - 0.1725) < 1e-10


def test_pixel_size_with_binning():
    """Same setup with 2x binning: 0.345 um"""
    obj = ObjectiveMetadata(
        name="20x",
        magnification=20.0,
        numerical_aperture=0.75,
        tube_lens_f_mm=200.0,
        sensor_pixel_size_um=3.45,
        camera_binning=2,
        tube_lens_mm=200.0,
    )
    assert abs(obj.pixel_size_um - 0.345) < 1e-10


def test_pixel_size_different_tube_lens():
    """20x with 180mm objective tube lens, 200mm system tube lens.
    lens_factor = 180 / 20 / 200 = 0.045
    dxy = 3.45 * 1 * 0.045 = 0.15525 um"""
    obj = ObjectiveMetadata(
        name="20x Nikon",
        magnification=20.0,
        numerical_aperture=0.75,
        tube_lens_f_mm=180.0,
        sensor_pixel_size_um=3.45,
        camera_binning=1,
        tube_lens_mm=200.0,
    )
    assert abs(obj.pixel_size_um - 0.15525) < 1e-10


def test_pixel_size_40x():
    """40x, 200mm/200mm tube lens, 3.45um sensor.
    dxy = 3.45 * (200/40/200) = 3.45 * 0.025 = 0.08625 um"""
    obj = ObjectiveMetadata(
        name="40x",
        magnification=40.0,
        numerical_aperture=1.3,
        tube_lens_f_mm=200.0,
        sensor_pixel_size_um=3.45,
        camera_binning=1,
        tube_lens_mm=200.0,
    )
    assert abs(obj.pixel_size_um - 0.08625) < 1e-10
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/test_data_model.py tests/unit/test_pixel_size.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'squid_tools.core.data_model'`

- [ ] **Step 4: Implement data_model.py**

```python
# squid_tools/core/data_model.py
"""Shared Pydantic v2 data models for Squid acquisitions.

All enums use ALL_CAPS to match Squid's internal conventions.
Derived values (e.g. pixel_size_um) are computed fields that match
Squid's ObjectiveStore calculations exactly.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal, NamedTuple

from pydantic import BaseModel, computed_field


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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pixel_size_um(self) -> float:
        """dxy at sample plane. Matches Squid ObjectiveStore calculation."""
        lens_factor = self.tube_lens_f_mm / self.magnification / self.tube_lens_mm
        return self.sensor_pixel_size_um * self.camera_binning * lens_factor


class OpticalMetadata(BaseModel):
    modality: Literal[
        "widefield", "confocal", "two_photon", "lightsheet", "spinning_disk"
    ]
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
    region_id: str
    center_mm: tuple[float, float, float]
    shape: Literal["Square", "Rectangle", "Circle", "Manual"]
    fovs: list[FOVPosition]
    grid_params: GridParams | None = None


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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_data_model.py tests/unit/test_pixel_size.py -v`
Expected: all PASS

- [ ] **Step 6: Run ruff and mypy**

Run: `ruff check squid_tools/core/data_model.py && ruff format --check squid_tools/core/data_model.py`
Run: `mypy squid_tools/core/data_model.py`

- [ ] **Step 7: Commit**

```bash
git add squid_tools/core/data_model.py tests/unit/test_data_model.py tests/unit/test_pixel_size.py
git commit -m "feat: add Pydantic v2 data models with pixel size computation"
```

---

## Task 3: Synthetic Fixture Generator

**Files:**
- Create: `tests/fixtures/generate_fixtures.py`
- Create: `tests/conftest.py`

This generates realistic Squid acquisition directories (all 3 formats) for testing. Every subsequent test task depends on this.

- [ ] **Step 1: Write fixture generator**

```python
# tests/fixtures/generate_fixtures.py
"""Generate synthetic Squid acquisition directories for testing.

Creates realistic directory structures matching Squid's output for all 3 formats.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import tifffile
import yaml


def generate_acquisition_yaml(
    path: Path,
    widget_type: str = "wellplate",
    n_regions: int = 1,
    region_ids: list[str] | None = None,
    nx: int = 3,
    ny: int = 3,
    nz: int = 1,
    nt: int = 1,
    n_channels: int = 2,
    overlap_percent: float = 15.0,
    pixel_size_um: float = 0.1725,
    sensor_pixel_size_um: float = 3.45,
    magnification: float = 20.0,
) -> dict:
    """Write acquisition.yaml and return the config dict."""
    if region_ids is None:
        if widget_type == "wellplate":
            region_ids = [f"A{i+1}" for i in range(n_regions)]
        else:
            region_ids = [f"manual{i}" for i in range(n_regions)]

    channels = []
    channel_names = ["DAPI", "GFP", "RFP", "Cy5"][:n_channels]
    wavelengths = [405.0, 488.0, 561.0, 640.0][:n_channels]
    for i, (name, wl) in enumerate(zip(channel_names, wavelengths)):
        channels.append({
            "name": name,
            "illumination_source": f"LED_{int(wl)}",
            "illumination_intensity": 50.0,
            "exposure_time_ms": 100.0,
            "emission_wavelength_nm": wl + 50,
            "z_offset_um": 0.0,
        })

    config = {
        "acquisition": {
            "experiment_id": "test_acquisition",
            "widget_type": widget_type,
        },
        "objective": {
            "name": f"{int(magnification)}x",
            "magnification": magnification,
            "NA": 0.75,
            "sensor_pixel_size_um": sensor_pixel_size_um,
            "camera_binning": 1,
            "tube_lens_f_mm": 200.0,
        },
        "z_stack": {"nz": nz, "delta_z_mm": 0.001, "config": "FROM_BOTTOM", "use_piezo": False},
        "time_series": {"nt": nt, "delta_t_s": 30.0},
        "channels": channels,
    }

    if widget_type == "wellplate":
        config["wellplate_scan"] = {
            "scan_size_mm": 2.0,
            "overlap_percent": overlap_percent,
            "regions": [
                {"name": rid, "center_mm": [10.0 + i * 9.0, 20.0, 0.0], "shape": "Square"}
                for i, rid in enumerate(region_ids)
            ],
        }
    else:
        config["flexible_scan"] = {
            "nx": nx,
            "ny": ny,
            "delta_x_mm": pixel_size_um * 2048 * (1 - overlap_percent / 100) / 1000,
            "delta_y_mm": pixel_size_um * 2048 * (1 - overlap_percent / 100) / 1000,
            "overlap_percent": overlap_percent,
            "positions": [
                {"name": rid, "center_mm": [10.0 + i * 5.0, 20.0, 0.0]}
                for i, rid in enumerate(region_ids)
            ],
        }

    path.mkdir(parents=True, exist_ok=True)
    with open(path / "acquisition.yaml", "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    return config


def generate_coordinates_csv(
    path: Path,
    region_ids: list[str],
    nx: int = 3,
    ny: int = 3,
    nz: int = 1,
    pixel_size_um: float = 0.1725,
    overlap_percent: float = 15.0,
    img_width: int = 256,
) -> None:
    """Write coordinates.csv with grid FOV positions."""
    step_mm = pixel_size_um * img_width * (1 - overlap_percent / 100) / 1000
    lines = ["region,fov,z_level,x (mm),y (mm),z (um),time\n"]
    for region_id in region_ids:
        fov_idx = 0
        for row in range(ny):
            for col in range(nx):
                for z in range(nz):
                    x = 10.0 + col * step_mm
                    y = 20.0 + row * step_mm
                    lines.append(f"{region_id},{fov_idx},{z},{x:.6f},{y:.6f},0.0,0.0\n")
                fov_idx += 1
    with open(path / "coordinates.csv", "w") as f:
        f.writelines(lines)


def generate_acquisition_params_json(
    path: Path,
    sensor_pixel_size_um: float = 3.45,
    tube_lens_mm: float = 200.0,
) -> None:
    """Write acquisition parameters.json."""
    params = {
        "sensor_pixel_size_um": sensor_pixel_size_um,
        "tube_lens_mm": tube_lens_mm,
        "confocal_mode": False,
    }
    with open(path / "acquisition parameters.json", "w") as f:
        json.dump(params, f, indent=2)


def generate_individual_images(
    path: Path,
    region_ids: list[str],
    nx: int = 3,
    ny: int = 3,
    nz: int = 1,
    nt: int = 1,
    n_channels: int = 2,
    img_shape: tuple[int, int] = (256, 256),
) -> None:
    """Generate individual TIFF images matching Squid's naming convention."""
    for t in range(nt):
        t_dir = path / f"{t:05d}"
        t_dir.mkdir(parents=True, exist_ok=True)
        for region_id in region_ids:
            fov_idx = 0
            for _row in range(ny):
                for _col in range(nx):
                    for ch in range(n_channels):
                        img = np.random.randint(0, 4096, img_shape, dtype=np.uint16)
                        fname = f"{region_id}_{fov_idx:05d}_C{ch:02d}.tiff"
                        metadata = json.dumps({
                            "z_level": 0,
                            "channel": ch,
                            "channel_index": ch,
                            "region_id": region_id,
                            "fov": fov_idx,
                            "x_mm": 10.0,
                            "y_mm": 20.0,
                            "z_mm": 0.0,
                            "time": 0.0,
                        })
                        tifffile.imwrite(
                            t_dir / fname, img, description=metadata
                        )
                    fov_idx += 1


def generate_ome_tiff(
    path: Path,
    region_ids: list[str],
    nx: int = 3,
    ny: int = 3,
    nz: int = 1,
    nt: int = 1,
    n_channels: int = 2,
    img_shape: tuple[int, int] = (256, 256),
) -> None:
    """Generate OME-TIFF files matching Squid's naming convention."""
    ome_dir = path / "ome_tiff"
    ome_dir.mkdir(parents=True, exist_ok=True)
    for region_id in region_ids:
        fov_idx = 0
        for _row in range(ny):
            for _col in range(nx):
                fname = f"{region_id}_{fov_idx:05d}.ome.tiff"
                data = np.random.randint(
                    0, 4096,
                    (nt, nz, n_channels, *img_shape),
                    dtype=np.uint16,
                )
                metadata = {
                    "axes": "TZCYX",
                    "Channel": {"Name": ["DAPI", "GFP"][:n_channels]},
                    "PhysicalSizeX": 0.1725,
                    "PhysicalSizeXUnit": "µm",
                    "PhysicalSizeY": 0.1725,
                    "PhysicalSizeYUnit": "µm",
                }
                tifffile.imwrite(
                    ome_dir / fname,
                    data,
                    ome=True,
                    metadata=metadata,
                )
                fov_idx += 1


def create_test_acquisition(
    base_path: Path,
    fmt: str = "INDIVIDUAL_IMAGES",
    widget_type: str = "wellplate",
    n_regions: int = 1,
    nx: int = 3,
    ny: int = 3,
    nz: int = 1,
    nt: int = 1,
    n_channels: int = 2,
    img_shape: tuple[int, int] = (256, 256),
) -> Path:
    """Create a complete synthetic Squid acquisition directory.

    Args:
        base_path: Parent directory for the acquisition.
        fmt: "INDIVIDUAL_IMAGES", "OME_TIFF", or "ZARR".
        widget_type: "wellplate" or "flexible".
        n_regions: Number of regions/wells.
        nx, ny: Grid dimensions per region.
        nz, nt: Z-levels and timepoints.
        n_channels: Number of channels.
        img_shape: (height, width) of each frame.

    Returns:
        Path to the created acquisition directory.
    """
    acq_path = base_path / f"test_{fmt.lower()}_{widget_type}"
    acq_path.mkdir(parents=True, exist_ok=True)

    region_ids = (
        [f"A{i+1}" for i in range(n_regions)]
        if widget_type == "wellplate"
        else [f"manual{i}" for i in range(n_regions)]
    )

    generate_acquisition_yaml(
        acq_path,
        widget_type=widget_type,
        n_regions=n_regions,
        region_ids=region_ids,
        nx=nx,
        ny=ny,
        nz=nz,
        nt=nt,
        n_channels=n_channels,
    )
    generate_coordinates_csv(
        acq_path,
        region_ids=region_ids,
        nx=nx,
        ny=ny,
        nz=nz,
        img_width=img_shape[1],
    )
    generate_acquisition_params_json(acq_path)

    if fmt == "INDIVIDUAL_IMAGES":
        generate_individual_images(
            acq_path, region_ids, nx, ny, nz, nt, n_channels, img_shape
        )
    elif fmt == "OME_TIFF":
        generate_ome_tiff(
            acq_path, region_ids, nx, ny, nz, nt, n_channels, img_shape
        )
    elif fmt == "ZARR":
        pass  # Zarr fixture generation added when zarr reader is implemented

    return acq_path
```

- [ ] **Step 2: Write conftest.py with shared fixtures**

```python
# tests/conftest.py
from __future__ import annotations

import pytest
from pathlib import Path
from tests.fixtures.generate_fixtures import create_test_acquisition


@pytest.fixture
def tmp_acq_dir(tmp_path: Path) -> Path:
    return tmp_path / "acquisitions"


@pytest.fixture
def individual_wellplate(tmp_acq_dir: Path) -> Path:
    return create_test_acquisition(
        tmp_acq_dir, fmt="INDIVIDUAL_IMAGES", widget_type="wellplate",
        n_regions=2, nx=3, ny=3, nz=2, nt=1, n_channels=2,
    )


@pytest.fixture
def individual_tissue(tmp_acq_dir: Path) -> Path:
    return create_test_acquisition(
        tmp_acq_dir, fmt="INDIVIDUAL_IMAGES", widget_type="flexible",
        n_regions=1, nx=2, ny=2, nz=1, nt=1, n_channels=2,
    )


@pytest.fixture
def ome_tiff_wellplate(tmp_acq_dir: Path) -> Path:
    return create_test_acquisition(
        tmp_acq_dir, fmt="OME_TIFF", widget_type="wellplate",
        n_regions=2, nx=3, ny=3, nz=2, nt=1, n_channels=2,
    )


@pytest.fixture
def ome_tiff_tissue(tmp_acq_dir: Path) -> Path:
    return create_test_acquisition(
        tmp_acq_dir, fmt="OME_TIFF", widget_type="flexible",
        n_regions=1, nx=2, ny=2, nz=1, nt=1, n_channels=2,
    )


GPU_AVAILABLE = False
try:
    import cupy  # noqa: F401
    GPU_AVAILABLE = True
except ImportError:
    pass

gpu = pytest.mark.skipif(not GPU_AVAILABLE, reason="No NVIDIA GPU with CUDA")
```

- [ ] **Step 3: Verify fixture generation works**

Run: `pytest tests/conftest.py --collect-only`
Run: `python -c "from tests.fixtures.generate_fixtures import create_test_acquisition; from pathlib import Path; p = create_test_acquisition(Path('/tmp/test_fixture'), fmt='INDIVIDUAL_IMAGES'); print(p); import os; print(os.listdir(p))"`
Expected: directory listing with `acquisition.yaml`, `coordinates.csv`, `acquisition parameters.json`, `00000/`

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/generate_fixtures.py tests/conftest.py
git commit -m "feat: add synthetic Squid acquisition fixture generator"
```

---

## Task 4: Format Reader ABC + Auto-Detection

**Files:**
- Create: `squid_tools/core/readers/base.py`
- Create: `squid_tools/core/readers/detect.py`
- Create: `squid_tools/core/readers/__init__.py`
- Create: `tests/unit/test_readers.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_readers.py
import numpy as np
from squid_tools.core.readers.base import FormatReader, FrameKey
from squid_tools.core.readers.detect import detect_format, open_acquisition
from squid_tools.core.data_model import AcquisitionFormat


def test_format_reader_is_abstract():
    """FormatReader cannot be instantiated directly."""
    import pytest
    with pytest.raises(TypeError):
        FormatReader()  # type: ignore[abstract]


def test_detect_individual_images(individual_wellplate):
    fmt = detect_format(individual_wellplate)
    assert fmt == AcquisitionFormat.INDIVIDUAL_IMAGES


def test_detect_ome_tiff(ome_tiff_wellplate):
    fmt = detect_format(ome_tiff_wellplate)
    assert fmt == AcquisitionFormat.OME_TIFF


def test_open_acquisition_individual(individual_wellplate):
    acq = open_acquisition(individual_wellplate)
    assert acq.format == AcquisitionFormat.INDIVIDUAL_IMAGES
    assert acq.mode.value == "wellplate"
    assert len(acq.regions) == 2
    assert len(acq.channels) == 2


def test_open_acquisition_ome_tiff(ome_tiff_wellplate):
    acq = open_acquisition(ome_tiff_wellplate)
    assert acq.format == AcquisitionFormat.OME_TIFF
    assert len(acq.regions) == 2


def test_open_acquisition_tissue(individual_tissue):
    acq = open_acquisition(individual_tissue)
    assert acq.mode.value == "flexible"


def test_open_acquisition_pixel_size(individual_wellplate):
    acq = open_acquisition(individual_wellplate)
    assert abs(acq.objective.pixel_size_um - 0.1725) < 1e-6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_readers.py -v`
Expected: FAIL with import errors

- [ ] **Step 3: Implement FormatReader ABC**

```python
# squid_tools/core/readers/base.py
"""Abstract base class for format readers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np

from squid_tools.core.data_model import Acquisition, FrameKey


class FormatReader(ABC):
    """Base class for Squid acquisition format readers.

    Each reader knows how to detect its format and parse metadata
    from a Squid acquisition directory.
    """

    @classmethod
    @abstractmethod
    def detect(cls, path: Path) -> bool:
        """Return True if this reader can handle the acquisition at path."""
        ...

    @abstractmethod
    def read_metadata(self, path: Path) -> Acquisition:
        """Parse all metadata into the unified Acquisition model."""
        ...

    @abstractmethod
    def read_frame(self, path: Path, key: FrameKey) -> np.ndarray:
        """Load a single 2D frame identified by key."""
        ...
```

- [ ] **Step 4: Implement detect.py with metadata parsing**

```python
# squid_tools/core/readers/detect.py
"""Auto-detect acquisition format and parse metadata from acquisition.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml

from squid_tools.core.data_model import (
    Acquisition,
    AcquisitionChannel,
    AcquisitionFormat,
    AcquisitionMode,
    FOVPosition,
    ObjectiveMetadata,
    OpticalMetadata,
    Region,
    ScanConfig,
    TimeSeriesConfig,
    ZStackConfig,
)


def detect_format(path: Path) -> AcquisitionFormat:
    """Detect the acquisition format from directory contents."""
    if (path / "ome_tiff").is_dir():
        return AcquisitionFormat.OME_TIFF
    if (path / "plate.ome.zarr").exists() or (path / "zarr").is_dir():
        return AcquisitionFormat.ZARR
    # Check for timepoint directories with individual images
    for child in path.iterdir():
        if child.is_dir() and child.name.isdigit():
            tiffs = list(child.glob("*.tiff")) + list(child.glob("*.tif"))
            if tiffs:
                return AcquisitionFormat.INDIVIDUAL_IMAGES
    raise ValueError(f"Cannot detect acquisition format in {path}")


def _parse_coordinates_csv(path: Path) -> dict[str, list[FOVPosition]]:
    """Parse coordinates.csv into region -> list[FOVPosition]."""
    import csv

    fovs_by_region: dict[str, dict[int, FOVPosition]] = {}
    csv_path = path / "coordinates.csv"
    if not csv_path.exists():
        return {}

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            region_id = row["region"]
            fov_idx = int(row["fov"])
            if region_id not in fovs_by_region:
                fovs_by_region[region_id] = {}
            if fov_idx not in fovs_by_region[region_id]:
                fovs_by_region[region_id][fov_idx] = FOVPosition(
                    fov_index=fov_idx,
                    x_mm=float(row["x (mm)"]),
                    y_mm=float(row["y (mm)"]),
                    z_um=float(row.get("z (um)", 0)),
                    z_piezo_um=float(row["z_piezo (um)"])
                    if "z_piezo (um)" in row and row["z_piezo (um)"]
                    else None,
                )

    return {
        rid: list(fov_dict.values())
        for rid, fov_dict in fovs_by_region.items()
    }


IMMERSION_RI = {
    "air": 1.0,
    "water": 1.333,
    "oil": 1.515,
    "glycerol": 1.473,
    "silicone": 1.406,
}


def open_acquisition(path: Path) -> Acquisition:
    """Open a Squid acquisition directory and parse all metadata.

    Reads acquisition.yaml as the master metadata file,
    coordinates.csv for FOV positions, and acquisition parameters.json
    for hardware details.
    """
    fmt = detect_format(path)

    # Parse acquisition.yaml
    with open(path / "acquisition.yaml") as f:
        config = yaml.safe_load(f)

    # Determine mode
    acq_config = config.get("acquisition", {})
    widget_type = acq_config.get("widget_type", "flexible")
    mode = AcquisitionMode(widget_type) if widget_type in ("wellplate", "flexible") else AcquisitionMode.MANUAL

    # Parse objective
    obj_config = config.get("objective", {})
    tube_lens_mm = 200.0
    # Try to get tube_lens_mm from acquisition parameters.json
    params_path = path / "acquisition parameters.json"
    if params_path.exists():
        import json
        with open(params_path) as f:
            params = json.load(f)
        tube_lens_mm = params.get("tube_lens_mm", 200.0)

    objective = ObjectiveMetadata(
        name=obj_config.get("name", "unknown"),
        magnification=float(obj_config.get("magnification", 1.0)),
        numerical_aperture=float(obj_config.get("NA", 0.25)),
        tube_lens_f_mm=float(obj_config.get("tube_lens_f_mm", 200.0)),
        sensor_pixel_size_um=float(obj_config.get("sensor_pixel_size_um", 3.45)),
        camera_binning=int(obj_config.get("camera_binning", 1)),
        tube_lens_mm=tube_lens_mm,
    )

    # Parse channels
    channels = [
        AcquisitionChannel(
            name=ch["name"],
            illumination_source=ch.get("illumination_source", ""),
            illumination_intensity=float(ch.get("illumination_intensity", 0)),
            exposure_time_ms=float(ch.get("exposure_time_ms", 0)),
            emission_wavelength_nm=float(ch["emission_wavelength_nm"])
            if ch.get("emission_wavelength_nm")
            else None,
            z_offset_um=float(ch.get("z_offset_um", 0)),
        )
        for ch in config.get("channels", [])
    ]

    # Parse z-stack
    zs_config = config.get("z_stack")
    z_stack = None
    if zs_config and zs_config.get("nz", 1) > 1:
        z_stack = ZStackConfig(
            nz=zs_config["nz"],
            delta_z_mm=float(zs_config.get("delta_z_mm", 0.001)),
            direction=zs_config.get("config", "FROM_BOTTOM"),
            use_piezo=zs_config.get("use_piezo", False),
        )

    # Parse time series
    ts_config = config.get("time_series")
    time_series = None
    if ts_config and ts_config.get("nt", 1) > 1:
        time_series = TimeSeriesConfig(
            nt=ts_config["nt"],
            delta_t_s=float(ts_config.get("delta_t_s", 0)),
        )

    # Parse scan config
    overlap = None
    acq_pattern = "S-Pattern"
    fov_pattern = "Unidirectional"
    if "wellplate_scan" in config:
        overlap = config["wellplate_scan"].get("overlap_percent")
    elif "flexible_scan" in config:
        overlap = config["flexible_scan"].get("overlap_percent")

    scan = ScanConfig(
        acquisition_pattern=acq_pattern,
        fov_pattern=fov_pattern,
        overlap_percent=overlap,
    )

    # Parse regions from coordinates.csv + acquisition.yaml
    fovs_by_region = _parse_coordinates_csv(path)
    regions: dict[str, Region] = {}

    # Get region metadata from yaml
    region_configs = []
    if "wellplate_scan" in config:
        region_configs = config["wellplate_scan"].get("regions", [])
    elif "flexible_scan" in config:
        region_configs = config["flexible_scan"].get("positions", [])

    for rc in region_configs:
        rid = rc["name"]
        center = rc.get("center_mm", [0, 0, 0])
        shape = rc.get("shape", "Manual")
        fovs = fovs_by_region.get(rid, [])
        regions[rid] = Region(
            region_id=rid,
            center_mm=tuple(center),  # type: ignore[arg-type]
            shape=shape,
            fovs=fovs,
        )

    # If coordinates.csv has regions not in yaml, add them
    for rid, fovs in fovs_by_region.items():
        if rid not in regions:
            regions[rid] = Region(
                region_id=rid,
                center_mm=(0.0, 0.0, 0.0),
                shape="Manual",
                fovs=fovs,
            )

    # Build optical metadata
    optical = OpticalMetadata(
        modality="widefield",
        immersion_medium="air",
        immersion_ri=IMMERSION_RI["air"],
        numerical_aperture=objective.numerical_aperture,
        pixel_size_um=objective.pixel_size_um,
        dz_um=float(zs_config["delta_z_mm"]) * 1000 if zs_config else None,
    )

    return Acquisition(
        path=path,
        format=fmt,
        mode=mode,
        objective=objective,
        optical=optical,
        channels=channels,
        scan=scan,
        z_stack=z_stack,
        time_series=time_series,
        regions=regions,
    )
```

- [ ] **Step 5: Update readers __init__.py**

```python
# squid_tools/core/readers/__init__.py
from squid_tools.core.readers.base import FormatReader
from squid_tools.core.readers.detect import detect_format, open_acquisition

__all__ = ["FormatReader", "detect_format", "open_acquisition"]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_readers.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add squid_tools/core/readers/ tests/unit/test_readers.py
git commit -m "feat: add format reader ABC, auto-detection, and metadata parsing"
```

---

## Task 5: Memory-Bounded LRU Cache

**Files:**
- Create: `squid_tools/core/cache.py`
- Create: `tests/unit/test_cache.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_cache.py
import numpy as np
from squid_tools.core.cache import MemoryBoundedLRUCache


def test_cache_stores_and_retrieves():
    cache = MemoryBoundedLRUCache(max_memory_bytes=1024 * 1024)
    arr = np.zeros((10, 10), dtype=np.uint16)
    cache.put("key1", arr)
    result = cache.get("key1")
    assert result is not None
    np.testing.assert_array_equal(result, arr)


def test_cache_returns_none_for_missing_key():
    cache = MemoryBoundedLRUCache(max_memory_bytes=1024 * 1024)
    assert cache.get("nonexistent") is None


def test_cache_evicts_lru_when_full():
    max_bytes = 1000
    cache = MemoryBoundedLRUCache(max_memory_bytes=max_bytes)
    # Each array is 200 bytes (100 uint16 = 200 bytes)
    for i in range(6):
        cache.put(f"key{i}", np.zeros(100, dtype=np.uint16))
    # First entries should have been evicted
    assert cache.get("key0") is None
    assert cache.get("key5") is not None


def test_cache_rejects_oversized_item():
    cache = MemoryBoundedLRUCache(max_memory_bytes=100)
    big = np.zeros(1000, dtype=np.uint16)  # 2000 bytes
    cache.put("big", big)
    assert cache.get("big") is None


def test_cache_move_to_end_on_hit():
    cache = MemoryBoundedLRUCache(max_memory_bytes=800)
    # 3 items, each 200 bytes = 600 total
    for i in range(3):
        cache.put(f"key{i}", np.zeros(100, dtype=np.uint16))
    # Access key0 to move it to end
    cache.get("key0")
    # Add another item to force eviction
    cache.put("key3", np.zeros(100, dtype=np.uint16))
    cache.put("key4", np.zeros(100, dtype=np.uint16))
    # key1 should be evicted (LRU), key0 should survive (recently accessed)
    assert cache.get("key1") is None
    assert cache.get("key0") is not None


def test_cache_thread_safety():
    import threading
    cache = MemoryBoundedLRUCache(max_memory_bytes=1024 * 1024)
    errors = []

    def writer(start: int):
        try:
            for i in range(100):
                cache.put(f"w{start}_{i}", np.zeros(10, dtype=np.uint16))
        except Exception as e:
            errors.append(e)

    def reader(start: int):
        try:
            for i in range(100):
                cache.get(f"w{start}_{i}")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(j,)) for j in range(4)]
    threads += [threading.Thread(target=reader, args=(j,)) for j in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_cache.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement MemoryBoundedLRUCache**

```python
# squid_tools/core/cache.py
"""Memory-bounded LRU cache for numpy arrays.

Pattern from ndviewer_light: evicts by nbytes, not count.
Thread-safe via threading.Lock on all operations.
"""
from __future__ import annotations

import threading
from collections import OrderedDict

import numpy as np


class MemoryBoundedLRUCache:
    """LRU cache bounded by total memory usage of cached numpy arrays."""

    def __init__(self, max_memory_bytes: int = 256 * 1024 * 1024) -> None:
        self._max_memory = max_memory_bytes
        self._current_memory = 0
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> np.ndarray | None:
        with self._lock:
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return self._cache[key]

    def put(self, key: str, value: np.ndarray) -> None:
        item_bytes = value.nbytes
        if item_bytes > self._max_memory:
            return

        with self._lock:
            if key in self._cache:
                self._current_memory -= self._cache[key].nbytes
                del self._cache[key]

            while self._current_memory + item_bytes > self._max_memory and self._cache:
                _, evicted = self._cache.popitem(last=False)
                self._current_memory -= evicted.nbytes

            self._cache[key] = value
            self._current_memory += item_bytes

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._current_memory = 0

    @property
    def current_memory(self) -> int:
        return self._current_memory

    def __len__(self) -> int:
        return len(self._cache)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_cache.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add squid_tools/core/cache.py tests/unit/test_cache.py
git commit -m "feat: add memory-bounded LRU cache with thread safety"
```

---

## Task 6: TiffFile Handle Pool

**Files:**
- Create: `squid_tools/core/handle_pool.py`
- Create: `tests/unit/test_handle_pool.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_handle_pool.py
import numpy as np
import tifffile
from pathlib import Path
from squid_tools.core.handle_pool import TiffHandlePool


def _write_test_tiff(path: Path, data: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(str(path), data)


def test_pool_reads_file(tmp_path: Path):
    img = np.random.randint(0, 4096, (256, 256), dtype=np.uint16)
    fpath = tmp_path / "test.tiff"
    _write_test_tiff(fpath, img)

    pool = TiffHandlePool(max_handles=16)
    result = pool.read(fpath, page_index=0)
    np.testing.assert_array_equal(result, img)
    pool.close_all()


def test_pool_caches_handles(tmp_path: Path):
    img = np.zeros((64, 64), dtype=np.uint16)
    fpath = tmp_path / "test.tiff"
    _write_test_tiff(fpath, img)

    pool = TiffHandlePool(max_handles=16)
    pool.read(fpath, page_index=0)
    pool.read(fpath, page_index=0)
    assert pool.open_count == 1
    pool.close_all()


def test_pool_evicts_when_full(tmp_path: Path):
    pool = TiffHandlePool(max_handles=3)
    for i in range(5):
        fpath = tmp_path / f"test_{i}.tiff"
        _write_test_tiff(fpath, np.zeros((16, 16), dtype=np.uint16))
        pool.read(fpath, page_index=0)
    assert pool.open_count <= 3
    pool.close_all()


def test_pool_concurrent_reads(tmp_path: Path):
    import threading
    paths = []
    for i in range(10):
        fpath = tmp_path / f"test_{i}.tiff"
        _write_test_tiff(fpath, np.random.randint(0, 100, (32, 32), dtype=np.uint16))
        paths.append(fpath)

    pool = TiffHandlePool(max_handles=128)
    errors = []

    def reader(fpath: Path):
        try:
            for _ in range(20):
                pool.read(fpath, page_index=0)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=reader, args=(p,)) for p in paths]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 0
    pool.close_all()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_handle_pool.py -v`
Expected: FAIL

- [ ] **Step 3: Implement TiffHandlePool**

```python
# squid_tools/core/handle_pool.py
"""TiffFile handle pool with LRU eviction and per-file locking.

Pattern from ndviewer_light: 128-handle cap, per-file locks for
parallel reads across files while serializing same-file reads.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

import numpy as np
import tifffile


class TiffHandlePool:
    """Pool of open TiffFile handles with LRU eviction."""

    def __init__(self, max_handles: int = 128) -> None:
        self._max_handles = max_handles
        self._handles: OrderedDict[Path, tuple[tifffile.TiffFile, threading.Lock]] = OrderedDict()
        self._global_lock = threading.Lock()

    def read(self, path: Path, page_index: int = 0) -> np.ndarray:
        """Read a single page from a TIFF file, reusing cached handles."""
        path = path.resolve()
        file_lock = self._get_or_create_handle(path)
        with file_lock:
            tf, _ = self._handles[path]
            return tf.pages[page_index].asarray()

    def _get_or_create_handle(self, path: Path) -> threading.Lock:
        with self._global_lock:
            if path in self._handles:
                self._handles.move_to_end(path)
                return self._handles[path][1]

            # Evict if at capacity
            to_close = []
            while len(self._handles) >= self._max_handles:
                _, (old_tf, _) = self._handles.popitem(last=False)
                to_close.append(old_tf)

        # Close evicted handles outside global lock
        for tf in to_close:
            tf.close()

        tf = tifffile.TiffFile(str(path))
        lock = threading.Lock()

        with self._global_lock:
            self._handles[path] = (tf, lock)

        return lock

    @property
    def open_count(self) -> int:
        return len(self._handles)

    def close_all(self) -> None:
        with self._global_lock:
            for tf, _ in self._handles.values():
                tf.close()
            self._handles.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_handle_pool.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add squid_tools/core/handle_pool.py tests/unit/test_handle_pool.py
git commit -m "feat: add TiffFile handle pool with LRU eviction and per-file locking"
```

---

## Task 7: Individual Images Reader

**Files:**
- Create: `squid_tools/core/readers/individual.py`
- Modify: `tests/unit/test_readers.py` (add frame reading tests)

- [ ] **Step 1: Write failing tests for frame reading**

Add to `tests/unit/test_readers.py`:

```python
def test_individual_reader_read_frame(individual_wellplate):
    from squid_tools.core.readers.individual import IndividualImageReader
    from squid_tools.core.data_model import FrameKey

    reader = IndividualImageReader()
    assert reader.detect(individual_wellplate)
    key = FrameKey(region="A1", fov=0, z=0, channel=0, timepoint=0)
    frame = reader.read_frame(individual_wellplate, key)
    assert frame.shape == (256, 256)
    assert frame.dtype == np.uint16


def test_individual_reader_different_channels(individual_wellplate):
    from squid_tools.core.readers.individual import IndividualImageReader
    from squid_tools.core.data_model import FrameKey

    reader = IndividualImageReader()
    key_ch0 = FrameKey(region="A1", fov=0, z=0, channel=0, timepoint=0)
    key_ch1 = FrameKey(region="A1", fov=0, z=0, channel=1, timepoint=0)
    frame0 = reader.read_frame(individual_wellplate, key_ch0)
    frame1 = reader.read_frame(individual_wellplate, key_ch1)
    # Different channels should have different random data
    assert not np.array_equal(frame0, frame1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_readers.py::test_individual_reader_read_frame -v`
Expected: FAIL

- [ ] **Step 3: Implement IndividualImageReader**

```python
# squid_tools/core/readers/individual.py
"""Reader for Squid's individual image format.

File pattern: {timepoint}/{region}_{fov:05}_C{channel:02}.tiff
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import tifffile

from squid_tools.core.data_model import FrameKey
from squid_tools.core.readers.base import FormatReader


class IndividualImageReader(FormatReader):
    @classmethod
    def detect(cls, path: Path) -> bool:
        for child in path.iterdir():
            if child.is_dir() and child.name.isdigit():
                tiffs = list(child.glob("*.tiff")) + list(child.glob("*.tif"))
                if tiffs:
                    return True
        return False

    def read_metadata(self, path: Path) -> None:
        # Metadata parsing is in detect.py open_acquisition()
        raise NotImplementedError("Use open_acquisition() for metadata parsing")

    def read_frame(self, path: Path, key: FrameKey) -> np.ndarray:
        t_dir = path / f"{key.timepoint:05d}"
        fname = f"{key.region}_{key.fov:05d}_C{key.channel:02d}.tiff"
        fpath = t_dir / fname
        if not fpath.exists():
            raise FileNotFoundError(f"Frame not found: {fpath}")
        return tifffile.imread(str(fpath))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_readers.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add squid_tools/core/readers/individual.py tests/unit/test_readers.py
git commit -m "feat: add individual images reader"
```

---

## Task 8: OME-TIFF Reader

**Files:**
- Create: `squid_tools/core/readers/ome_tiff.py`
- Modify: `tests/unit/test_readers.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_readers.py`:

```python
def test_ome_tiff_reader_detect(ome_tiff_wellplate):
    from squid_tools.core.readers.ome_tiff import OMETiffReader
    assert OMETiffReader.detect(ome_tiff_wellplate)


def test_ome_tiff_reader_read_frame(ome_tiff_wellplate):
    from squid_tools.core.readers.ome_tiff import OMETiffReader
    from squid_tools.core.data_model import FrameKey

    reader = OMETiffReader()
    key = FrameKey(region="A1", fov=0, z=0, channel=0, timepoint=0)
    frame = reader.read_frame(ome_tiff_wellplate, key)
    assert frame.shape == (256, 256)
    assert frame.dtype == np.uint16


def test_ome_tiff_reader_z_channel_indexing(ome_tiff_wellplate):
    from squid_tools.core.readers.ome_tiff import OMETiffReader
    from squid_tools.core.data_model import FrameKey

    reader = OMETiffReader()
    key_z0 = FrameKey(region="A1", fov=0, z=0, channel=0, timepoint=0)
    key_z1 = FrameKey(region="A1", fov=0, z=1, channel=0, timepoint=0)
    frame_z0 = reader.read_frame(ome_tiff_wellplate, key_z0)
    frame_z1 = reader.read_frame(ome_tiff_wellplate, key_z1)
    assert not np.array_equal(frame_z0, frame_z1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_readers.py::test_ome_tiff_reader_detect -v`
Expected: FAIL

- [ ] **Step 3: Implement OMETiffReader**

```python
# squid_tools/core/readers/ome_tiff.py
"""Reader for Squid's OME-TIFF format.

File pattern: ome_tiff/{region}_{fov:05}.ome.tiff
Axis order: TZCYX
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import tifffile

from squid_tools.core.data_model import FrameKey
from squid_tools.core.readers.base import FormatReader


class OMETiffReader(FormatReader):
    @classmethod
    def detect(cls, path: Path) -> bool:
        ome_dir = path / "ome_tiff"
        if not ome_dir.is_dir():
            return False
        return any(ome_dir.glob("*.ome.tiff")) or any(ome_dir.glob("*.ome.tif"))

    def read_metadata(self, path: Path) -> None:
        raise NotImplementedError("Use open_acquisition() for metadata parsing")

    def read_frame(self, path: Path, key: FrameKey) -> np.ndarray:
        ome_dir = path / "ome_tiff"
        fname = f"{key.region}_{key.fov:05d}.ome.tiff"
        fpath = ome_dir / fname
        if not fpath.exists():
            raise FileNotFoundError(f"OME-TIFF not found: {fpath}")

        with tifffile.TiffFile(str(fpath)) as tf:
            # OME-TIFF axis order: TZCYX
            data = tf.asarray()
            if data.ndim == 5:
                # (T, Z, C, Y, X)
                return data[key.timepoint, key.z, key.channel]
            elif data.ndim == 4:
                # (Z, C, Y, X) - single timepoint
                return data[key.z, key.channel]
            elif data.ndim == 3:
                # (C, Y, X) - single z, single timepoint
                return data[key.channel]
            else:
                return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_readers.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add squid_tools/core/readers/ome_tiff.py tests/unit/test_readers.py
git commit -m "feat: add OME-TIFF reader"
```

---

## Task 9: Plugin ABC

**Files:**
- Create: `squid_tools/plugins/base.py`
- Create: `tests/unit/test_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_registry.py
import pytest
import numpy as np
from pydantic import BaseModel
from squid_tools.plugins.base import ProcessingPlugin, TestCase


def test_plugin_is_abstract():
    with pytest.raises(TypeError):
        ProcessingPlugin()  # type: ignore[abstract]


def test_test_case_model():
    tc = TestCase(
        name="identity",
        input_shape=(1, 1, 1, 64, 64),
        input_dtype="uint16",
        description="Passthrough test",
    )
    assert tc.input_shape == (1, 1, 1, 64, 64)


def test_concrete_plugin():
    class DummyParams(BaseModel):
        sigma: float = 1.0

    class DummyPlugin(ProcessingPlugin):
        name = "Dummy"
        category = "correction"
        requires_gpu = False

        def parameters(self) -> type[BaseModel]:
            return DummyParams

        def validate(self, acq):
            return []

        def process(self, frames, params):
            return frames

        def default_params(self, optical):
            return DummyParams()

        def test_cases(self) -> list[TestCase]:
            return [TestCase(
                name="passthrough",
                input_shape=(1, 1, 1, 64, 64),
                input_dtype="uint16",
                description="Returns input unchanged",
            )]

    plugin = DummyPlugin()
    assert plugin.name == "Dummy"
    assert plugin.parameters() is DummyParams
    assert len(plugin.test_cases()) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_registry.py -v`
Expected: FAIL

- [ ] **Step 3: Implement ProcessingPlugin ABC**

```python
# squid_tools/plugins/base.py
"""ProcessingPlugin abstract base class.

Every processing module implements this interface.
Wrapping a new algorithm = one file, one class, ~50 lines.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import dask.array as da
from pydantic import BaseModel

from squid_tools.core.data_model import Acquisition, OpticalMetadata


class TestCase(BaseModel):
    """Defines a synthetic test scenario for a plugin."""
    name: str
    input_shape: tuple[int, ...]
    input_dtype: str = "uint16"
    description: str = ""


class ProcessingPlugin(ABC):
    """Base class for all processing plugins.

    Subclasses must set class attributes:
        name: Human-readable plugin name
        category: "stitching" | "deconvolution" | "correction" | "phase"
        requires_gpu: Whether GPU is needed (False = CPU only)
    """
    name: str
    category: str
    requires_gpu: bool = False

    @abstractmethod
    def parameters(self) -> type[BaseModel]:
        """Return the Pydantic model class for this plugin's parameters."""
        ...

    @abstractmethod
    def validate(self, acq: Acquisition) -> list[str]:
        """Check if this plugin can run on the given acquisition.
        Return list of warning/error messages (empty = ok)."""
        ...

    @abstractmethod
    def process(self, frames: da.Array, params: BaseModel) -> da.Array:
        """Transform frames. Lazy dask in, lazy dask out."""
        ...

    @abstractmethod
    def default_params(self, optical: OpticalMetadata) -> BaseModel:
        """Auto-populate parameters from acquisition metadata."""
        ...

    @abstractmethod
    def test_cases(self) -> list[TestCase]:
        """Return synthetic test case definitions for unit tests."""
        ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_registry.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add squid_tools/plugins/base.py tests/unit/test_registry.py
git commit -m "feat: add ProcessingPlugin ABC with TestCase model"
```

---

## Task 10: OME Sidecar

**Files:**
- Create: `squid_tools/core/sidecar.py`
- Create: `tests/unit/test_sidecar.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_sidecar.py
import json
from pathlib import Path
from squid_tools.core.sidecar import SidecarManager, ProcessingRun


def test_sidecar_creates_directory(tmp_path: Path):
    acq_path = tmp_path / "test_acquisition"
    acq_path.mkdir()
    mgr = SidecarManager(acq_path)
    mgr.ensure_directory()
    assert (acq_path / ".squid-tools").is_dir()
    assert (acq_path / ".squid-tools" / "manifest.json").exists()


def test_sidecar_records_run(tmp_path: Path):
    acq_path = tmp_path / "test_acquisition"
    acq_path.mkdir()
    mgr = SidecarManager(acq_path)
    mgr.ensure_directory()
    mgr.record_run(ProcessingRun(
        plugin="TileFusion Stitcher",
        version="0.3.1",
        params={"overlap_percent": 15},
        output_path="stitcher/",
    ))
    manifest = mgr.load_manifest()
    assert len(manifest["runs"]) == 1
    assert manifest["runs"][0]["plugin"] == "TileFusion Stitcher"


def test_sidecar_multiple_runs(tmp_path: Path):
    acq_path = tmp_path / "test_acquisition"
    acq_path.mkdir()
    mgr = SidecarManager(acq_path)
    mgr.ensure_directory()
    mgr.record_run(ProcessingRun(plugin="A", version="1.0", params={}, output_path="a/"))
    mgr.record_run(ProcessingRun(plugin="B", version="2.0", params={}, output_path="b/"))
    manifest = mgr.load_manifest()
    assert len(manifest["runs"]) == 2


def test_sidecar_plugin_output_dir(tmp_path: Path):
    acq_path = tmp_path / "test_acquisition"
    acq_path.mkdir()
    mgr = SidecarManager(acq_path)
    out_dir = mgr.plugin_output_dir("stitcher")
    assert out_dir == acq_path / ".squid-tools" / "stitcher"
    assert out_dir.is_dir()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_sidecar.py -v`
Expected: FAIL

- [ ] **Step 3: Implement SidecarManager**

```python
# squid_tools/core/sidecar.py
"""OME Sidecar: non-destructive output alongside Squid acquisitions.

Processing results and provenance metadata live in .squid-tools/
within the acquisition directory. Original files are never modified.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class ProcessingRun(BaseModel):
    """Record of a single processing operation."""
    plugin: str
    version: str
    params: dict[str, Any]
    output_path: str
    timestamp: str = ""
    input_hash: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class SidecarManager:
    """Manages the .squid-tools sidecar directory."""

    def __init__(self, acquisition_path: Path) -> None:
        self._acq_path = acquisition_path
        self._sidecar_path = acquisition_path / ".squid-tools"
        self._manifest_path = self._sidecar_path / "manifest.json"

    def ensure_directory(self) -> None:
        self._sidecar_path.mkdir(exist_ok=True)
        if not self._manifest_path.exists():
            self._write_manifest({"runs": []})

    def record_run(self, run: ProcessingRun) -> None:
        manifest = self.load_manifest()
        manifest["runs"].append(run.model_dump())
        self._write_manifest(manifest)

    def load_manifest(self) -> dict[str, Any]:
        if not self._manifest_path.exists():
            return {"runs": []}
        with open(self._manifest_path) as f:
            return json.load(f)

    def plugin_output_dir(self, plugin_name: str) -> Path:
        out_dir = self._sidecar_path / plugin_name
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        self._sidecar_path.mkdir(exist_ok=True)
        with open(self._manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_sidecar.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add squid_tools/core/sidecar.py tests/unit/test_sidecar.py
git commit -m "feat: add OME sidecar manager for non-destructive output"
```

---

## Task 11: Plugin Registry

**Files:**
- Create: `squid_tools/core/registry.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_registry.py`:

```python
from squid_tools.core.registry import discover_plugins


def test_discover_plugins_returns_dict():
    plugins = discover_plugins()
    assert isinstance(plugins, dict)
```

- [ ] **Step 2: Implement registry**

```python
# squid_tools/core/registry.py
"""Plugin discovery via Python entry_points."""
from __future__ import annotations

import importlib.metadata

from squid_tools.plugins.base import ProcessingPlugin


def discover_plugins() -> dict[str, ProcessingPlugin]:
    """Discover all installed plugins via entry_points."""
    plugins: dict[str, ProcessingPlugin] = {}
    eps = importlib.metadata.entry_points()
    squid_eps = eps.select(group="squid_tools.plugins") if hasattr(eps, "select") else eps.get("squid_tools.plugins", [])
    for ep in squid_eps:
        try:
            plugin_cls = ep.load()
            if isinstance(plugin_cls, type) and issubclass(plugin_cls, ProcessingPlugin):
                instance = plugin_cls()
                plugins[ep.name] = instance
        except Exception:
            continue
    return plugins
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_registry.py -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add squid_tools/core/registry.py tests/unit/test_registry.py
git commit -m "feat: add plugin discovery via entry_points"
```

---

## Task 12: Processing Pipeline

**Files:**
- Create: `squid_tools/core/pipeline.py`
- Create: `tests/unit/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_pipeline.py
import numpy as np
import dask.array as da
from pydantic import BaseModel
from squid_tools.core.pipeline import Pipeline
from squid_tools.plugins.base import ProcessingPlugin, TestCase


class ScaleParams(BaseModel):
    factor: float = 2.0


class ScalePlugin(ProcessingPlugin):
    name = "Scale"
    category = "correction"

    def parameters(self):
        return ScaleParams

    def validate(self, acq):
        return []

    def process(self, frames, params):
        return frames * params.factor

    def default_params(self, optical):
        return ScaleParams()

    def test_cases(self):
        return [TestCase(name="scale", input_shape=(1, 1, 1, 8, 8), input_dtype="float64")]


def test_pipeline_single_plugin():
    data = da.from_array(np.ones((1, 1, 1, 8, 8), dtype=np.float64))
    pipe = Pipeline()
    pipe.add(ScalePlugin(), ScaleParams(factor=3.0))
    result = pipe.run(data)
    np.testing.assert_array_equal(result.compute(), np.full((1, 1, 1, 8, 8), 3.0))


def test_pipeline_chained():
    data = da.from_array(np.ones((1, 1, 1, 8, 8), dtype=np.float64))
    pipe = Pipeline()
    pipe.add(ScalePlugin(), ScaleParams(factor=2.0))
    pipe.add(ScalePlugin(), ScaleParams(factor=3.0))
    result = pipe.run(data)
    np.testing.assert_array_equal(result.compute(), np.full((1, 1, 1, 8, 8), 6.0))


def test_pipeline_empty():
    data = da.from_array(np.ones((1, 1, 1, 8, 8), dtype=np.float64))
    pipe = Pipeline()
    result = pipe.run(data)
    np.testing.assert_array_equal(result.compute(), data.compute())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_pipeline.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Pipeline**

```python
# squid_tools/core/pipeline.py
"""Processing pipeline: chain plugins, lazy dask in/out."""
from __future__ import annotations

import dask.array as da
from pydantic import BaseModel

from squid_tools.plugins.base import ProcessingPlugin


class PipelineStep:
    def __init__(self, plugin: ProcessingPlugin, params: BaseModel) -> None:
        self.plugin = plugin
        self.params = params


class Pipeline:
    """Chain of processing plugins applied sequentially."""

    def __init__(self) -> None:
        self._steps: list[PipelineStep] = []

    def add(self, plugin: ProcessingPlugin, params: BaseModel) -> None:
        self._steps.append(PipelineStep(plugin, params))

    def run(self, frames: da.Array) -> da.Array:
        result = frames
        for step in self._steps:
            result = step.plugin.process(result, step.params)
        return result

    def clear(self) -> None:
        self._steps.clear()

    @property
    def steps(self) -> list[PipelineStep]:
        return list(self._steps)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_pipeline.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add squid_tools/core/pipeline.py tests/unit/test_pipeline.py
git commit -m "feat: add processing pipeline for chaining plugins"
```

---

## Task 13: Background Subtraction Plugin

**Files:**
- Create: `squid_tools/plugins/background.py`
- Create: `tests/integration/test_background.py`

This is the simplest plugin. It validates the plugin pattern end-to-end before wiring up the harder ones.

- [ ] **Step 1: Write failing tests**

```python
# tests/integration/test_background.py
import numpy as np
import dask.array as da
from squid_tools.plugins.background import BackgroundPlugin, BackgroundParams


def test_background_plugin_attributes():
    plugin = BackgroundPlugin()
    assert plugin.name == "Background Subtraction"
    assert plugin.category == "correction"
    assert plugin.requires_gpu is False


def test_background_plugin_parameters():
    plugin = BackgroundPlugin()
    assert plugin.parameters() is BackgroundParams


def test_background_plugin_default_params():
    plugin = BackgroundPlugin()
    params = plugin.default_params(None)  # type: ignore[arg-type]
    assert isinstance(params, BackgroundParams)


def test_background_plugin_process():
    plugin = BackgroundPlugin()
    params = BackgroundParams()
    # Create synthetic image with a bright object on a background
    img = np.zeros((1, 1, 1, 64, 64), dtype=np.float64)
    img[:, :, :, :, :] = 100.0  # background level
    img[:, :, :, 20:40, 20:40] = 500.0  # bright object
    frames = da.from_array(img)
    result = plugin.process(frames, params).compute()
    # After background subtraction, the background should be near zero
    # and the object should be positive
    assert result[0, 0, 0, 30, 30] > result[0, 0, 0, 5, 5]


def test_background_plugin_test_cases():
    plugin = BackgroundPlugin()
    cases = plugin.test_cases()
    assert len(cases) >= 1
    assert cases[0].name != ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_background.py -v`
Expected: FAIL

- [ ] **Step 3: Implement BackgroundPlugin**

```python
# squid_tools/plugins/background.py
"""Background subtraction plugin wrapping sep (Source Extractor for Python)."""
from __future__ import annotations

import dask.array as da
import numpy as np
from pydantic import BaseModel

from squid_tools.core.data_model import Acquisition, OpticalMetadata
from squid_tools.plugins.base import ProcessingPlugin, TestCase


class BackgroundParams(BaseModel):
    box_size: int = 64
    filter_size: int = 3


class BackgroundPlugin(ProcessingPlugin):
    name = "Background Subtraction"
    category = "correction"
    requires_gpu = False

    def parameters(self) -> type[BaseModel]:
        return BackgroundParams

    def validate(self, acq: Acquisition) -> list[str]:
        return []

    def default_params(self, optical: OpticalMetadata) -> BackgroundParams:
        return BackgroundParams()

    def process(self, frames: da.Array, params: BaseModel) -> da.Array:
        assert isinstance(params, BackgroundParams)
        return frames.map_blocks(
            _subtract_background,
            dtype=frames.dtype,
            bw=params.box_size,
            fw=params.filter_size,
        )

    def test_cases(self) -> list[TestCase]:
        return [
            TestCase(
                name="uniform_background",
                input_shape=(1, 1, 1, 64, 64),
                input_dtype="float64",
                description="Uniform background with bright object, background should be reduced",
            ),
        ]


def _subtract_background(
    block: np.ndarray, bw: int = 64, fw: int = 3
) -> np.ndarray:
    """Subtract background from a single block using sep."""
    try:
        import sep
    except ImportError:
        raise ImportError("sep is required for background subtraction: pip install sep")

    result = np.empty_like(block)
    original_shape = block.shape
    # Process each 2D frame in the block
    it = np.nditer(
        [np.empty(original_shape[:-2])],
        flags=["multi_index"],
    )
    for _ in it:
        idx = it.multi_index
        frame = block[idx].astype(np.float64, copy=True)
        # Ensure C-contiguous for sep
        frame = np.ascontiguousarray(frame)
        bkg = sep.Background(frame, bw=bw, bh=bw, fw=fw, fh=fw)
        result[idx] = frame - bkg.back()
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pip install sep && pytest tests/integration/test_background.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add squid_tools/plugins/background.py tests/integration/test_background.py
git commit -m "feat: add background subtraction plugin wrapping sep"
```

---

## Task 14: Flatfield Correction Plugin

**Files:**
- Create: `squid_tools/plugins/flatfield.py`
- Create: `tests/integration/test_flatfield.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/integration/test_flatfield.py
import numpy as np
import dask.array as da
from squid_tools.plugins.flatfield import FlatfieldPlugin, FlatfieldParams


def test_flatfield_plugin_attributes():
    plugin = FlatfieldPlugin()
    assert plugin.name == "Flatfield Correction"
    assert plugin.category == "correction"


def test_flatfield_plugin_process():
    plugin = FlatfieldPlugin()
    params = FlatfieldParams()
    # Simulate non-uniform illumination
    y, x = np.mgrid[0:64, 0:64]
    illumination = 1.0 + 0.3 * np.sin(x * np.pi / 64)
    signal = np.ones((64, 64), dtype=np.float64) * 1000
    img = (signal * illumination).reshape(1, 1, 1, 64, 64)
    frames = da.from_array(img)
    result = plugin.process(frames, params).compute()
    # After correction, variance across the image should be reduced
    original_std = np.std(img[0, 0, 0])
    corrected_std = np.std(result[0, 0, 0])
    assert corrected_std < original_std


def test_flatfield_plugin_test_cases():
    plugin = FlatfieldPlugin()
    assert len(plugin.test_cases()) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_flatfield.py -v`
Expected: FAIL

- [ ] **Step 3: Implement FlatfieldPlugin**

```python
# squid_tools/plugins/flatfield.py
"""Flatfield correction plugin wrapping BaSiCPy."""
from __future__ import annotations

import dask.array as da
import numpy as np
from pydantic import BaseModel

from squid_tools.core.data_model import Acquisition, OpticalMetadata
from squid_tools.plugins.base import ProcessingPlugin, TestCase


class FlatfieldParams(BaseModel):
    """Parameters for BaSiCPy flatfield estimation."""
    smoothness_flatfield: float = 1.0
    max_iterations: int = 500


class FlatfieldPlugin(ProcessingPlugin):
    name = "Flatfield Correction"
    category = "correction"
    requires_gpu = False

    def parameters(self) -> type[BaseModel]:
        return FlatfieldParams

    def validate(self, acq: Acquisition) -> list[str]:
        warnings = []
        # Need multiple FOVs for reliable flatfield estimation
        total_fovs = sum(len(r.fovs) for r in acq.regions.values())
        if total_fovs < 4:
            warnings.append("Flatfield correction works best with >= 4 FOVs")
        return warnings

    def default_params(self, optical: OpticalMetadata) -> FlatfieldParams:
        return FlatfieldParams()

    def process(self, frames: da.Array, params: BaseModel) -> da.Array:
        assert isinstance(params, FlatfieldParams)
        # Estimate flatfield from the stack, then apply correction
        # For now, use a simple mean-based flatfield estimation
        # BaSiCPy integration can be swapped in when available
        return frames.map_blocks(
            _estimate_and_correct_flatfield,
            dtype=np.float64,
        )

    def test_cases(self) -> list[TestCase]:
        return [
            TestCase(
                name="non_uniform_illumination",
                input_shape=(1, 1, 1, 64, 64),
                input_dtype="float64",
                description="Sinusoidal illumination pattern, correction should reduce variance",
            ),
        ]


def _estimate_and_correct_flatfield(block: np.ndarray) -> np.ndarray:
    """Simple mean-based flatfield correction for a block.

    For production, replace with BaSiCPy's estimate when multiple FOVs
    are available. This single-image version uses Gaussian smoothing
    as a flatfield estimate.
    """
    from scipy.ndimage import gaussian_filter

    result = np.empty_like(block, dtype=np.float64)
    original_shape = block.shape
    it = np.nditer(
        [np.empty(original_shape[:-2])],
        flags=["multi_index"],
    )
    for _ in it:
        idx = it.multi_index
        frame = block[idx].astype(np.float64)
        flatfield = gaussian_filter(frame, sigma=min(frame.shape) // 4)
        flatfield_norm = flatfield / flatfield.mean()
        flatfield_norm = np.where(flatfield_norm > 0.1, flatfield_norm, 1.0)
        result[idx] = frame / flatfield_norm
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_flatfield.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add squid_tools/plugins/flatfield.py tests/integration/test_flatfield.py
git commit -m "feat: add flatfield correction plugin"
```

---

## Task 15: GUI Main Window Shell

**Files:**
- Create: `squid_tools/gui/app.py`
- Create: `squid_tools/gui/log_panel.py`
- Create: `squid_tools/gui/controls.py`
- Create: `squid_tools/gui/processing_tabs.py`
- Create: `squid_tools/gui/wellplate.py`

This task creates the main window layout with all panels as placeholders.
The GUI should be launchable and show the layout structure from the spec:
processing tabs (top), controls (left), viewer (center), region selector (right), log (bottom).

- [ ] **Step 1: Implement log panel**

```python
# squid_tools/gui/log_panel.py
"""Bottom log/status panel."""
from __future__ import annotations

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt


class LogPanel(QWidget):
    """Status bar with log messages, GPU status, and memory usage."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)

        self._status = QLabel("Ready")
        self._status.setToolTip("Current status")
        layout.addWidget(self._status)

        layout.addStretch()

        self._gpu = QLabel(self._detect_gpu())
        self._gpu.setToolTip("GPU detection status")
        layout.addWidget(self._gpu)

        self._memory = QLabel("Mem: 0 MB")
        self._memory.setToolTip("Cache memory usage")
        layout.addWidget(self._memory)

    def set_status(self, msg: str) -> None:
        self._status.setText(msg)

    def set_memory(self, used_mb: float, total_mb: float) -> None:
        self._memory.setText(f"Mem: {used_mb:.1f}/{total_mb:.0f} MB")

    def _detect_gpu(self) -> str:
        try:
            import cupy
            device = cupy.cuda.Device(0)
            name = device.attributes.get("DeviceName", "GPU")
            return f"GPU: {cupy.cuda.runtime.getDeviceProperties(0)['name'].decode()}"
        except Exception:
            return "GPU: not detected (CPU mode)"
```

- [ ] **Step 2: Implement controls panel**

```python
# squid_tools/gui/controls.py
"""Left controls panel: FOV/mosaic toggle, borders, layers."""
from __future__ import annotations

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QCheckBox, QLabel, QGroupBox,
)
from PyQt5.QtCore import pyqtSignal


class ControlsPanel(QWidget):
    """Left panel with viewer controls."""
    view_mode_changed = pyqtSignal(str)  # "fov" or "mosaic"
    borders_toggled = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(160)
        layout = QVBoxLayout(self)

        # View mode toggle
        view_group = QGroupBox("View")
        view_layout = QVBoxLayout(view_group)
        self._fov_btn = QPushButton("Single FOV")
        self._fov_btn.setToolTip("View single field of view with full 5D navigation")
        self._fov_btn.setCheckable(True)
        self._fov_btn.setChecked(True)
        self._fov_btn.clicked.connect(lambda: self._set_mode("fov"))
        view_layout.addWidget(self._fov_btn)

        self._mosaic_btn = QPushButton("Mosaic")
        self._mosaic_btn.setToolTip("View tiled mosaic assembled from stage coordinates")
        self._mosaic_btn.setCheckable(True)
        self._mosaic_btn.clicked.connect(lambda: self._set_mode("mosaic"))
        view_layout.addWidget(self._mosaic_btn)
        layout.addWidget(view_group)

        # Border overlay
        overlay_group = QGroupBox("Overlay")
        overlay_layout = QVBoxLayout(overlay_group)
        self._borders_cb = QCheckBox("FOV Borders")
        self._borders_cb.setToolTip("Show/hide FOV boundary rectangles")
        self._borders_cb.setChecked(False)
        self._borders_cb.toggled.connect(self.borders_toggled.emit)
        overlay_layout.addWidget(self._borders_cb)
        layout.addWidget(overlay_group)

        # Layers
        layers_group = QGroupBox("Layers")
        self._layers_layout = QVBoxLayout(layers_group)
        self._layers_layout.addWidget(QLabel("No layers"))
        layout.addWidget(layers_group)

        layout.addStretch()

    def _set_mode(self, mode: str) -> None:
        self._fov_btn.setChecked(mode == "fov")
        self._mosaic_btn.setChecked(mode == "mosaic")
        self.view_mode_changed.emit(mode)
```

- [ ] **Step 3: Implement well plate / region selector**

```python
# squid_tools/gui/wellplate.py
"""Right panel: well plate grid or region dropdown.

Auto-detects wellplate vs tissue from acquisition.yaml widget_type.
"""
from __future__ import annotations

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QPushButton, QComboBox,
    QLabel, QGroupBox, QStackedWidget,
)
from PyQt5.QtCore import pyqtSignal

from squid_tools.core.data_model import Acquisition, AcquisitionMode


class WellplateGrid(QWidget):
    """Clickable well plate grid."""
    well_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QGridLayout(self)
        self._buttons: dict[str, QPushButton] = {}

    def set_wells(self, well_ids: list[str], rows: int = 8, cols: int = 12) -> None:
        # Clear existing
        for btn in self._buttons.values():
            self._layout.removeWidget(btn)
            btn.deleteLater()
        self._buttons.clear()

        for well_id in well_ids:
            row_letter = well_id[0]
            col_num = int(well_id[1:]) - 1
            row_idx = ord(row_letter) - ord("A")
            btn = QPushButton(well_id)
            btn.setFixedSize(36, 28)
            btn.setToolTip(f"Select region {well_id}")
            btn.clicked.connect(lambda checked, w=well_id: self.well_selected.emit(w))
            self._layout.addWidget(btn, row_idx, col_num)
            self._buttons[well_id] = btn

    def highlight_well(self, well_id: str) -> None:
        for wid, btn in self._buttons.items():
            btn.setStyleSheet(
                "background-color: #4a9eff;" if wid == well_id else ""
            )


class RegionDropdown(QWidget):
    """Dropdown for tissue/manual regions."""
    region_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Region:"))
        self._combo = QComboBox()
        self._combo.setToolTip("Select acquisition region")
        self._combo.currentTextChanged.connect(self.region_selected.emit)
        layout.addWidget(self._combo)
        layout.addStretch()

    def set_regions(self, region_ids: list[str]) -> None:
        self._combo.clear()
        self._combo.addItems(region_ids)


class RegionSelector(QWidget):
    """Right panel: auto-switches between wellplate grid and region dropdown."""
    region_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(200)
        layout = QVBoxLayout(self)

        group = QGroupBox("Region Selector")
        group_layout = QVBoxLayout(group)

        self._stack = QStackedWidget()
        self._wellplate = WellplateGrid()
        self._wellplate.well_selected.connect(self.region_selected.emit)
        self._dropdown = RegionDropdown()
        self._dropdown.region_selected.connect(self.region_selected.emit)
        self._stack.addWidget(self._wellplate)
        self._stack.addWidget(self._dropdown)
        group_layout.addWidget(self._stack)

        layout.addWidget(group)
        layout.addStretch()

    def set_acquisition(self, acq: Acquisition) -> None:
        region_ids = list(acq.regions.keys())
        if acq.mode == AcquisitionMode.WELLPLATE:
            self._wellplate.set_wells(region_ids)
            self._stack.setCurrentWidget(self._wellplate)
        else:
            self._dropdown.set_regions(region_ids)
            self._stack.setCurrentWidget(self._dropdown)
```

- [ ] **Step 4: Implement processing tabs**

```python
# squid_tools/gui/processing_tabs.py
"""Top tab bar: one tab per installed plugin with auto-generated param widgets."""
from __future__ import annotations

from PyQt5.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QPushButton, QFormLayout,
    QDoubleSpinBox, QSpinBox, QCheckBox, QLabel, QComboBox,
)
from PyQt5.QtCore import pyqtSignal
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from squid_tools.plugins.base import ProcessingPlugin


class PluginTab(QWidget):
    """Single plugin tab with auto-generated parameter widgets and Run button."""
    run_clicked = pyqtSignal(str, BaseModel)  # plugin_name, params

    def __init__(
        self, plugin: ProcessingPlugin, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._plugin = plugin
        self._param_cls = plugin.parameters()
        self._widgets: dict[str, QWidget] = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Auto-generate widgets from Pydantic model fields
        for field_name, field_info in self._param_cls.model_fields.items():
            widget = self._create_widget(field_name, field_info)
            if widget:
                label = field_name.replace("_", " ").title()
                form.addRow(label + ":", widget)
                self._widgets[field_name] = widget

        layout.addLayout(form)

        self._run_btn = QPushButton("Run")
        self._run_btn.setToolTip(f"Apply {plugin.name} to current view")
        self._run_btn.clicked.connect(self._on_run)
        layout.addWidget(self._run_btn)

        layout.addStretch()

    def _create_widget(self, name: str, field_info: FieldInfo) -> QWidget | None:
        annotation = field_info.annotation
        default = field_info.default

        if annotation is float or annotation == float:
            w = QDoubleSpinBox()
            w.setRange(-1e6, 1e6)
            w.setDecimals(4)
            if default is not None:
                w.setValue(float(default))
            w.setToolTip(field_info.description or f"Parameter: {name}")
            return w
        elif annotation is int or annotation == int:
            w = QSpinBox()
            w.setRange(0, 100000)
            if default is not None:
                w.setValue(int(default))
            w.setToolTip(field_info.description or f"Parameter: {name}")
            return w
        elif annotation is bool or annotation == bool:
            w = QCheckBox()
            if default is not None:
                w.setChecked(bool(default))
            w.setToolTip(field_info.description or f"Parameter: {name}")
            return w
        return None

    def _on_run(self) -> None:
        params_dict = {}
        for field_name, widget in self._widgets.items():
            if isinstance(widget, QDoubleSpinBox):
                params_dict[field_name] = widget.value()
            elif isinstance(widget, QSpinBox):
                params_dict[field_name] = widget.value()
            elif isinstance(widget, QCheckBox):
                params_dict[field_name] = widget.isChecked()
        params = self._param_cls(**params_dict)
        self.run_clicked.emit(self._plugin.name, params)

    def get_params(self) -> BaseModel:
        params_dict = {}
        for field_name, widget in self._widgets.items():
            if isinstance(widget, QDoubleSpinBox):
                params_dict[field_name] = widget.value()
            elif isinstance(widget, QSpinBox):
                params_dict[field_name] = widget.value()
            elif isinstance(widget, QCheckBox):
                params_dict[field_name] = widget.isChecked()
        return self._param_cls(**params_dict)


class ProcessingTabs(QTabWidget):
    """Top tab bar with one tab per installed plugin."""
    run_requested = pyqtSignal(str, BaseModel)  # plugin_name, params

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMaximumHeight(200)
        self._tabs: dict[str, PluginTab] = {}

    def add_plugin(self, plugin: ProcessingPlugin) -> None:
        tab = PluginTab(plugin)
        tab.run_clicked.connect(self.run_requested.emit)
        self.addTab(tab, plugin.name)
        self._tabs[plugin.name] = tab
```

- [ ] **Step 5: Implement main window**

```python
# squid_tools/gui/app.py
"""Main application window for squid-tools."""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFileDialog, QAction, QMenuBar,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from squid_tools.core.registry import discover_plugins
from squid_tools.core.readers import open_acquisition
from squid_tools.gui.controls import ControlsPanel
from squid_tools.gui.log_panel import LogPanel
from squid_tools.gui.processing_tabs import ProcessingTabs
from squid_tools.gui.wellplate import RegionSelector


class MainWindow(QMainWindow):
    """Squid-Tools main application window.

    Layout: processing tabs (top), controls (left), viewer (center),
    region selector (right), log (bottom).
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Squid-Tools")
        self.setMinimumSize(1200, 800)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Processing tabs (top)
        self._processing_tabs = ProcessingTabs()
        self._load_plugins()
        main_layout.addWidget(self._processing_tabs)

        # Middle section: controls | viewer | region selector
        middle = QHBoxLayout()
        middle.setSpacing(0)

        # Controls (left)
        self._controls = ControlsPanel()
        middle.addWidget(self._controls)

        # Viewer (center) - placeholder
        self._viewer_placeholder = QLabel("Open an acquisition to begin")
        self._viewer_placeholder.setAlignment(Qt.AlignCenter)
        self._viewer_placeholder.setFont(QFont("", 14))
        self._viewer_placeholder.setStyleSheet(
            "background-color: #1a1a2e; color: #888; border: 1px solid #333;"
        )
        middle.addWidget(self._viewer_placeholder, stretch=1)

        # Region selector (right)
        self._region_selector = RegionSelector()
        middle.addWidget(self._region_selector)

        main_layout.addLayout(middle, stretch=1)

        # Log panel (bottom)
        self._log = LogPanel()
        main_layout.addWidget(self._log)

        # Menu bar
        self._setup_menu()

        # Connections
        self._controls.view_mode_changed.connect(self._on_view_mode_changed)
        self._region_selector.region_selected.connect(self._on_region_selected)
        self._processing_tabs.run_requested.connect(self._on_run_plugin)

        self._acquisition = None

    def _setup_menu(self) -> None:
        menu = self.menuBar()
        file_menu = menu.addMenu("File")

        open_action = QAction("Open Acquisition...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.setToolTip("Open a Squid acquisition directory")
        open_action.triggered.connect(self._open_acquisition)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _load_plugins(self) -> None:
        plugins = discover_plugins()
        for name, plugin in plugins.items():
            self._processing_tabs.add_plugin(plugin)
        if not plugins:
            self._log.set_status("No plugins found. Install plugins or use --dev mode.")

    def _open_acquisition(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(
            self, "Open Squid Acquisition Directory"
        )
        if not dir_path:
            return
        try:
            self._acquisition = open_acquisition(Path(dir_path))
            self._region_selector.set_acquisition(self._acquisition)
            self._log.set_status(
                f"Opened: {self._acquisition.path.name} "
                f"({self._acquisition.format.value}, "
                f"{len(self._acquisition.regions)} regions)"
            )
        except Exception as e:
            self._log.set_status(f"Error: {e}")

    def _on_view_mode_changed(self, mode: str) -> None:
        self._log.set_status(f"View mode: {mode}")

    def _on_region_selected(self, region_id: str) -> None:
        self._log.set_status(f"Selected region: {region_id}")

    def _on_run_plugin(self, plugin_name: str, params) -> None:
        self._log.set_status(f"Running {plugin_name}...")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Squid-Tools")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Verify the GUI launches**

Run: `python -m squid_tools.gui.app`
Expected: Window opens with processing tabs (top), controls (left), viewer placeholder (center), region selector (right), log (bottom). Close it manually.

- [ ] **Step 7: Commit**

```bash
git add squid_tools/gui/
git commit -m "feat: add GUI main window with controls, processing tabs, region selector, log"
```

---

## Tasks 16-20: Remaining Implementation

The following tasks follow the same TDD pattern. Each task has: failing test, implementation, verify pass, commit.

### Task 16: Stitcher Plugin
- Create `squid_tools/plugins/stitcher.py` wrapping TileFusion
- Create `tests/integration/test_stitcher.py`
- StitcherPlugin implements ProcessingPlugin ABC
- Parameters: overlap_percent, registration (bool), output_format ("OME_TIFF")
- process() calls TileFusion's registration and fusion

### Task 17: Deconvolution Plugin
- Create `squid_tools/plugins/decon.py` wrapping PetaKit
- Create `tests/integration/test_decon.py`
- Parameters: modality, iterations, regularization, emission_wavelength_nm
- default_params() auto-fills from OpticalMetadata
- validate() checks for z-stack data

### Task 18: Mosaic View (napari)
- Create `squid_tools/gui/mosaic.py`
- Places FOV tiles at coordinates via napari translate transforms
- Dask-backed lazy loading per tile
- FOV border overlay as napari Shapes layer
- Integrate into MainWindow replacing viewer placeholder

### Task 19: Single FOV Viewer
- Create `squid_tools/gui/viewer.py` wrapping ndviewer_light
- 5D navigation (T, Z, C sliders)
- Toggle between viewer.py and mosaic.py via controls panel

### Task 20: Embeddable Widget + Distribution
- Create `squid_tools/gui/embed.py` with SquidToolsWidget(parent)
- Create `installer/entry.py` for PyInstaller frozen exe
- Create `installer/squid_tools.spec` PyInstaller spec
- Create GitHub Actions workflow for Windows .exe and Linux .AppImage builds

---

## Full Test Suite Verification

After all tasks are complete:

- [ ] Run: `ruff check squid_tools/ tests/`
- [ ] Run: `ruff format --check squid_tools/ tests/`
- [ ] Run: `mypy squid_tools/`
- [ ] Run: `pytest tests/ -v --tb=short`
- [ ] Run: `python -m squid_tools.gui.app` (manual GUI smoke test)

Expected: All pass. GUI launches, shows layout, opens a synthetic acquisition, displays regions.
