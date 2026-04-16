# Squid-Tools Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core library (zero GUI dependencies) that reads Squid acquisition formats, provides a plugin interface, and outputs to an OME sidecar.

**Architecture:** Pydantic v2 data model parses Squid's `acquisition.yaml` as the master metadata source. Format readers (ABC pattern) provide lazy dask-backed frame access. Plugins transform dask arrays through a pipeline. Results go to an OME sidecar directory.

**Tech Stack:** Python 3.10+, pydantic 2.x, dask, numpy, tifffile, zarr, pyyaml, pytest, ruff, mypy

**Spec:** `docs/superpowers/specs/2026-04-07-squid-tools-design.md`

---

## File Structure

```
squid_tools/
├── __init__.py                          # Package init, version
├── core/
│   ├── __init__.py
│   ├── data_model.py                    # All Pydantic v2 models
│   ├── readers/
│   │   ├── __init__.py                  # Re-exports detect_reader()
│   │   ├── base.py                      # FormatReader ABC, FrameKey
│   │   ├── individual.py               # IndividualImageReader
│   │   ├── ome_tiff.py                  # OMETiffReader
│   │   └── zarr_reader.py              # ZarrReader
│   ├── cache.py                         # MemoryBoundedLRUCache
│   ├── handle_pool.py                   # TiffFileHandlePool
│   ├── pipeline.py                      # Pipeline (chain plugins)
│   ├── sidecar.py                       # OME sidecar manifest
│   └── registry.py                      # Plugin discovery
├── plugins/
│   ├── __init__.py
│   └── base.py                          # ProcessingPlugin ABC
├── py.typed                             # PEP 561 marker
tests/
├── __init__.py
├── conftest.py                          # Shared fixtures
├── fixtures/
│   ├── __init__.py
│   └── generate_fixtures.py             # Synthetic Squid acquisitions
├── unit/
│   ├── __init__.py
│   ├── test_data_model.py
│   ├── test_pixel_size.py
│   ├── test_readers.py
│   ├── test_cache.py
│   ├── test_handle_pool.py
│   ├── test_pipeline.py
│   ├── test_sidecar.py
│   └── test_registry.py
└── integration/
    └── __init__.py
pyproject.toml                           # Build config, deps, ruff, mypy
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `squid_tools/__init__.py`
- Create: `squid_tools/core/__init__.py`
- Create: `squid_tools/core/readers/__init__.py`
- Create: `squid_tools/plugins/__init__.py`
- Create: `squid_tools/py.typed`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/fixtures/__init__.py`
- Create: `.gitignore`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "squid-tools"
version = "0.1.0"
description = "Post-processing connector for Cephla-Lab/Squid microscopy"
requires-python = ">=3.10"
dependencies = [
    "pydantic>=2.10",
    "numpy>=1.24",
    "dask[array]>=2024.1",
    "tifffile>=2024.1",
    "pyyaml>=6.0",
    "zarr>=2.16",
]

[project.optional-dependencies]
gpu = ["cupy-cuda12x>=13.0"]
dev = [
    "pytest>=8.0",
    "ruff>=0.4",
    "mypy>=1.10",
]

[project.entry-points."squid_tools.plugins"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.10"
strict = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "gpu: requires CUDA GPU",
]
```

- [ ] **Step 2: Create package init files**

`squid_tools/__init__.py`:
```python
"""Squid-Tools: Post-processing connector for Cephla-Lab/Squid."""

__version__ = "0.1.0"
```

`squid_tools/core/__init__.py`:
```python
"""Core library. Zero GUI dependencies."""
```

`squid_tools/core/readers/__init__.py`:
```python
"""Format readers for Squid acquisition data."""
```

`squid_tools/plugins/__init__.py`:
```python
"""Processing plugins."""
```

`squid_tools/py.typed`: empty file (PEP 561 marker)

`tests/__init__.py`: empty file
`tests/unit/__init__.py`: empty file
`tests/integration/__init__.py`: empty file
`tests/fixtures/__init__.py`: empty file

- [ ] **Step 3: Create .gitignore**

```
__pycache__/
*.pyc
.mypy_cache/
.pytest_cache/
.ruff_cache/
*.egg-info/
dist/
build/
.DS_Store
_audit/
.worktrees/
```

- [ ] **Step 4: Create tests/conftest.py**

```python
"""Shared test fixtures for squid-tools."""

from pathlib import Path

import pytest


@pytest.fixture
def tmp_acquisition(tmp_path: Path) -> Path:
    """Return a temporary directory for creating test acquisitions."""
    return tmp_path / "test_acquisition"
```

- [ ] **Step 5: Install in dev mode and verify**

Run: `pip install -e ".[dev]"`
Expected: Successful install

Run: `pytest --co -q`
Expected: `no tests ran` (no test files yet, but pytest itself works)

Run: `ruff check squid_tools/`
Expected: Clean (no errors)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml squid_tools/ tests/ .gitignore
git commit -m "feat: project scaffolding with pyproject.toml, package structure, dev tooling"
```

---

### Task 2: Data Model (Pydantic v2)

**Files:**
- Create: `squid_tools/core/data_model.py`
- Create: `tests/unit/test_data_model.py`
- Create: `tests/unit/test_pixel_size.py`

- [ ] **Step 1: Write failing tests for enums and basic models**

`tests/unit/test_data_model.py`:
```python
"""Tests for the Pydantic v2 data model."""

from squid_tools.core.data_model import (
    AcquisitionChannel,
    AcquisitionFormat,
    AcquisitionMode,
    FOVPosition,
    GridParams,
    ObjectiveMetadata,
    Region,
    ScanConfig,
    ZStackConfig,
    TimeSeriesConfig,
)


class TestEnums:
    def test_acquisition_format_values(self) -> None:
        assert AcquisitionFormat.OME_TIFF == "OME_TIFF"
        assert AcquisitionFormat.INDIVIDUAL_IMAGES == "INDIVIDUAL_IMAGES"
        assert AcquisitionFormat.ZARR == "ZARR"

    def test_acquisition_mode_values(self) -> None:
        assert AcquisitionMode.WELLPLATE == "wellplate"
        assert AcquisitionMode.FLEXIBLE == "flexible"
        assert AcquisitionMode.MANUAL == "manual"


class TestObjectiveMetadata:
    def test_create_objective(self) -> None:
        obj = ObjectiveMetadata(
            name="20x",
            magnification=20.0,
            pixel_size_um=0.325,
            numerical_aperture=0.75,
        )
        assert obj.name == "20x"
        assert obj.magnification == 20.0
        assert obj.pixel_size_um == 0.325
        assert obj.numerical_aperture == 0.75

    def test_optional_fields_default_none(self) -> None:
        obj = ObjectiveMetadata(
            name="10x",
            magnification=10.0,
            pixel_size_um=0.65,
        )
        assert obj.numerical_aperture is None
        assert obj.tube_lens_f_mm is None
        assert obj.sensor_pixel_size_um is None
        assert obj.camera_binning == 1


class TestAcquisitionChannel:
    def test_create_channel(self) -> None:
        ch = AcquisitionChannel(
            name="BF LED matrix full",
            illumination_source="LED matrix",
            illumination_intensity=50.0,
            exposure_time_ms=10.0,
        )
        assert ch.name == "BF LED matrix full"
        assert ch.emission_wavelength_nm is None
        assert ch.z_offset_um == 0.0


class TestFOVPosition:
    def test_create_fov(self) -> None:
        fov = FOVPosition(fov_index=0, x_mm=1.5, y_mm=2.3)
        assert fov.fov_index == 0
        assert fov.z_um is None

    def test_fov_with_z(self) -> None:
        fov = FOVPosition(fov_index=3, x_mm=1.0, y_mm=2.0, z_um=100.0, z_piezo_um=5.0)
        assert fov.z_um == 100.0
        assert fov.z_piezo_um == 5.0


class TestRegion:
    def test_create_wellplate_region(self) -> None:
        region = Region(
            region_id="A1",
            center_mm=(10.0, 20.0, 0.0),
            shape="Square",
            fovs=[FOVPosition(fov_index=0, x_mm=9.5, y_mm=19.5)],
            grid_params=GridParams(scan_size_mm=1.0, overlap_percent=15.0, nx=3, ny=3),
        )
        assert region.region_id == "A1"
        assert region.grid_params is not None
        assert region.grid_params.nx == 3

    def test_create_manual_region(self) -> None:
        region = Region(
            region_id="manual0",
            center_mm=(5.0, 5.0, 0.0),
            shape="Manual",
            fovs=[FOVPosition(fov_index=0, x_mm=5.0, y_mm=5.0)],
        )
        assert region.grid_params is None


class TestScanConfig:
    def test_default_scan(self) -> None:
        scan = ScanConfig(
            acquisition_pattern="S-Pattern",
            fov_pattern="Unidirectional",
        )
        assert scan.overlap_percent is None


class TestZStackConfig:
    def test_create_zstack(self) -> None:
        zs = ZStackConfig(nz=10, delta_z_mm=0.001, direction="FROM_BOTTOM")
        assert zs.use_piezo is False


class TestTimeSeriesConfig:
    def test_create_timeseries(self) -> None:
        ts = TimeSeriesConfig(nt=100, delta_t_s=0.5)
        assert ts.nt == 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_data_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'squid_tools.core.data_model'`

- [ ] **Step 3: Write minimal data model implementation**

`squid_tools/core/data_model.py`:
```python
"""Pydantic v2 data models for Squid acquisition metadata.

All models match Squid's acquisition.yaml structure. Field names follow
Squid's conventions. Derived values (like pixel_size_um) come directly
from Squid's pre-computed values in acquisition.yaml.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal, NamedTuple

from pydantic import BaseModel


class AcquisitionFormat(str, Enum):
    OME_TIFF = "OME_TIFF"
    INDIVIDUAL_IMAGES = "INDIVIDUAL_IMAGES"
    ZARR = "ZARR"


class AcquisitionMode(str, Enum):
    WELLPLATE = "wellplate"
    FLEXIBLE = "flexible"
    MANUAL = "manual"


class ObjectiveMetadata(BaseModel):
    """Objective info from acquisition.yaml -> objective section.

    pixel_size_um comes directly from Squid (pre-computed).
    NA, tube lens, sensor pixel size are optional because Squid's
    acquisition.yaml does not always include them.
    """

    name: str
    magnification: float
    pixel_size_um: float
    numerical_aperture: float | None = None
    tube_lens_f_mm: float | None = None
    sensor_pixel_size_um: float | None = None
    camera_binning: int = 1


class OpticalMetadata(BaseModel):
    """Optical parameters for processing plugins (e.g., deconvolution).

    These are NOT all available from Squid files. The user or GUI
    must supply modality, immersion medium, and RI. Emission wavelength
    comes from channel config if available.
    """

    modality: Literal[
        "widefield", "confocal", "two_photon", "lightsheet", "spinning_disk"
    ] | None = None
    immersion_medium: Literal["air", "water", "oil", "glycerol", "silicone"] | None = None
    immersion_ri: float | None = None
    numerical_aperture: float | None = None
    pixel_size_um: float | None = None
    dz_um: float | None = None


class AcquisitionChannel(BaseModel):
    """Channel from acquisition.yaml -> channels list."""

    name: str
    illumination_source: str = ""
    illumination_intensity: float = 0.0
    exposure_time_ms: float = 0.0
    emission_wavelength_nm: float | None = None
    z_offset_um: float = 0.0


class ScanConfig(BaseModel):
    """Scan pattern from acquisition.yaml."""

    acquisition_pattern: Literal["S-Pattern", "Unidirectional"] = "S-Pattern"
    fov_pattern: Literal["S-Pattern", "Unidirectional"] = "Unidirectional"
    overlap_percent: float | None = None


class GridParams(BaseModel):
    """Grid parameters for wellplate/flexible grid regions."""

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
    """Single field-of-view position from coordinates.csv."""

    fov_index: int
    x_mm: float
    y_mm: float
    z_um: float | None = None
    z_piezo_um: float | None = None


class Region(BaseModel):
    """A region (well, manual ROI, or flexible scan position)."""

    region_id: str
    center_mm: tuple[float, float, float]
    shape: Literal["Square", "Rectangle", "Circle", "Manual"] = "Square"
    fovs: list[FOVPosition] = []
    grid_params: GridParams | None = None


class ZStackConfig(BaseModel):
    """Z-stack configuration from acquisition.yaml."""

    nz: int
    delta_z_mm: float
    direction: Literal["FROM_BOTTOM", "FROM_TOP"] = "FROM_BOTTOM"
    use_piezo: bool = False


class TimeSeriesConfig(BaseModel):
    """Time series configuration from acquisition.yaml."""

    nt: int
    delta_t_s: float


class Acquisition(BaseModel):
    """Top-level entry point. One per dataset.

    Parsed from acquisition.yaml + coordinates.csv + format-specific files.
    """

    path: Path
    format: AcquisitionFormat
    mode: AcquisitionMode
    objective: ObjectiveMetadata
    optical: OpticalMetadata = OpticalMetadata()
    channels: list[AcquisitionChannel] = []
    scan: ScanConfig = ScanConfig()
    z_stack: ZStackConfig | None = None
    time_series: TimeSeriesConfig | None = None
    regions: dict[str, Region] = {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_data_model.py -v`
Expected: All tests PASS

- [ ] **Step 5: Write pixel_size_um derivation test**

`tests/unit/test_pixel_size.py`:
```python
"""Tests for derived pixel size calculation.

Squid pre-computes pixel_size_um in acquisition.yaml, so normally we
trust that value. But when raw sensor/objective params are available,
we should be able to derive it ourselves using Squid's formula:
    pixel_size_um = sensor_pixel_size_um * binning * (tube_lens_f_mm / magnification / tube_lens_mm)
"""

import math

from squid_tools.core.data_model import ObjectiveMetadata


def test_pixel_size_from_squid_value() -> None:
    """Trust Squid's pre-computed pixel_size_um."""
    obj = ObjectiveMetadata(name="20x", magnification=20.0, pixel_size_um=0.325)
    assert obj.pixel_size_um == 0.325


def test_derive_pixel_size_when_params_available() -> None:
    """Derive pixel_size_um from sensor/objective params (Squid ObjectiveStore formula)."""
    obj = ObjectiveMetadata(
        name="20x",
        magnification=20.0,
        pixel_size_um=0.325,
        sensor_pixel_size_um=3.45,
        tube_lens_f_mm=180.0,
        tube_lens_mm=50.0,
        camera_binning=1,
    )
    # Squid formula: sensor * binning * (obj_tube_lens / mag / sys_tube_lens)
    expected = 3.45 * 1 * (180.0 / 20.0 / 50.0)
    assert math.isclose(obj.derived_pixel_size_um, expected, rel_tol=1e-6)


def test_derived_pixel_size_returns_none_without_params() -> None:
    """Returns None when raw params not available."""
    obj = ObjectiveMetadata(name="20x", magnification=20.0, pixel_size_um=0.325)
    assert obj.derived_pixel_size_um is None
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/unit/test_pixel_size.py -v`
Expected: FAIL with `AttributeError: 'ObjectiveMetadata' object has no attribute 'derived_pixel_size_um'`

- [ ] **Step 7: Add derived_pixel_size_um to ObjectiveMetadata**

Add to `squid_tools/core/data_model.py` in the `ObjectiveMetadata` class:

```python
    @property
    def derived_pixel_size_um(self) -> float | None:
        """Derive pixel size from raw params using Squid's ObjectiveStore formula.

        Returns None if sensor_pixel_size_um, tube_lens_f_mm, or tube_lens_mm
        are not available.
        """
        if (
            self.sensor_pixel_size_um is None
            or self.tube_lens_f_mm is None
            or self.tube_lens_mm is None
        ):
            return None
        lens_factor = self.tube_lens_f_mm / self.magnification / self.tube_lens_mm
        return self.sensor_pixel_size_um * self.camera_binning * lens_factor
```

Also add `tube_lens_mm: float | None = None` field to ObjectiveMetadata (after `sensor_pixel_size_um`).

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/unit/test_data_model.py tests/unit/test_pixel_size.py -v`
Expected: All PASS

- [ ] **Step 9: Run ruff and mypy**

Run: `ruff check squid_tools/core/data_model.py`
Expected: Clean

Run: `mypy squid_tools/core/data_model.py`
Expected: Clean (or only pydantic plugin warnings)

- [ ] **Step 10: Commit**

```bash
git add squid_tools/core/data_model.py tests/unit/test_data_model.py tests/unit/test_pixel_size.py
git commit -m "feat: Pydantic v2 data model with all Squid acquisition types"
```

---

### Task 3: Fixture Generator

**Files:**
- Create: `tests/fixtures/generate_fixtures.py`
- Modify: `tests/conftest.py`

The fixture generator creates synthetic Squid acquisition directories with valid metadata files. All readers and integration tests depend on this.

- [ ] **Step 1: Write test for fixture generator**

Add to `tests/unit/test_data_model.py`:
```python
from tests.fixtures.generate_fixtures import create_individual_acquisition
from pathlib import Path


class TestFixtureGenerator:
    def test_creates_acquisition_yaml(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1)
        assert (acq_path / "acquisition.yaml").exists()

    def test_creates_coordinates_csv(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1)
        assert (acq_path / "0" / "coordinates.csv").exists()

    def test_creates_image_files(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1)
        tiffs = list((acq_path / "0").glob("*.tiff"))
        assert len(tiffs) == 4  # 2x2 FOVs * 1 channel
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_data_model.py::TestFixtureGenerator -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Write fixture generator**

`tests/fixtures/generate_fixtures.py`:
```python
"""Generate synthetic Squid acquisition directories for testing.

Creates realistic directory structures matching Squid's output,
including acquisition.yaml, coordinates.csv, and image files.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import tifffile
import yaml


def create_individual_acquisition(
    path: Path,
    nx: int = 3,
    ny: int = 3,
    nz: int = 1,
    nc: int = 1,
    nt: int = 1,
    image_shape: tuple[int, int] = (128, 128),
    overlap_percent: float = 15.0,
    wellplate: bool = True,
    region_id: str = "0",
) -> Path:
    """Create a synthetic Squid INDIVIDUAL_IMAGES acquisition.

    Args:
        path: Root directory for the acquisition.
        nx: Number of FOVs in X.
        ny: Number of FOVs in Y.
        nz: Number of Z levels.
        nc: Number of channels.
        nt: Number of timepoints.
        image_shape: (height, width) of each image.
        overlap_percent: Overlap between tiles.
        wellplate: If True, widget_type="wellplate". Else "flexible".
        region_id: Region identifier (e.g., "0", "A1").

    Returns:
        Path to the created acquisition directory.
    """
    path.mkdir(parents=True, exist_ok=True)

    pixel_size_um = 0.325
    step_mm = pixel_size_um * image_shape[1] * (1 - overlap_percent / 100) / 1000
    channel_names = [f"channel_{i}" for i in range(nc)]

    # Build FOV positions
    fov_positions: list[dict[str, float]] = []
    center_x = nx * step_mm / 2
    center_y = ny * step_mm / 2
    for iy in range(ny):
        for ix in range(nx):
            fov_positions.append({
                "x_mm": ix * step_mm,
                "y_mm": iy * step_mm,
            })

    # Write acquisition.yaml
    acq_yaml = {
        "acquisition": {
            "experiment_id": "test_acquisition",
            "start_time": "2026-01-01T00:00:00",
            "widget_type": "wellplate" if wellplate else "flexible",
        },
        "objective": {
            "name": "20x",
            "magnification": 20.0,
            "pixel_size_um": pixel_size_um,
        },
        "z_stack": {
            "nz": nz,
            "delta_z_mm": 0.001,
            "config": "FROM_BOTTOM",
            "use_piezo": False,
        },
        "time_series": {
            "nt": nt,
            "delta_t_s": 1.0,
        },
        "channels": [
            {
                "name": name,
                "enabled": True,
                "camera_settings": {"exposure_time_ms": 10.0},
                "illumination_settings": {
                    "illumination_channel": f"LED_{i}",
                    "intensity": 50.0,
                },
                "z_offset_um": 0.0,
            }
            for i, name in enumerate(channel_names)
        ],
    }

    if wellplate:
        acq_yaml["wellplate_scan"] = {
            "scan_size_mm": nx * step_mm,
            "overlap_percent": overlap_percent,
            "regions": [
                {"name": region_id, "center_mm": [center_x, center_y, 0.0], "shape": "Square"}
            ],
        }
    else:
        acq_yaml["flexible_scan"] = {
            "nx": nx,
            "ny": ny,
            "delta_x_mm": step_mm,
            "delta_y_mm": step_mm,
            "overlap_percent": overlap_percent,
            "positions": [{"name": region_id, "center_mm": [center_x, center_y, 0.0]}],
        }

    with open(path / "acquisition.yaml", "w") as f:
        yaml.dump(acq_yaml, f, default_flow_style=False)

    # Write acquisition parameters.json
    acq_params = {
        "sensor_pixel_size_um": 3.45,
        "tube_lens_mm": 50.0,
    }
    with open(path / "acquisition parameters.json", "w") as f:
        json.dump(acq_params, f)

    # Write images and coordinates per timepoint
    for t in range(nt):
        tp_dir = path / str(t)
        tp_dir.mkdir(exist_ok=True)

        rows: list[dict[str, object]] = []
        fov_idx = 0
        for pos in fov_positions:
            for z in range(nz):
                for c, ch_name in enumerate(channel_names):
                    # Squid filename pattern: {region}_{fov}_{z}_{channel}.tiff
                    fname = f"{region_id}_{fov_idx}_{z}_{ch_name}.tiff"
                    img = np.random.randint(0, 4095, image_shape, dtype=np.uint16)
                    tifffile.imwrite(str(tp_dir / fname), img)

                rows.append({
                    "region": region_id,
                    "fov": fov_idx,
                    "z_level": z,
                    "x (mm)": pos["x_mm"],
                    "y (mm)": pos["y_mm"],
                    "z (um)": z * 1.0,
                    "time": t * 1.0,
                })
            fov_idx += 1

        # Write coordinates.csv
        with open(tp_dir / "coordinates.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    return path


def create_ome_tiff_acquisition(
    path: Path,
    nx: int = 2,
    ny: int = 2,
    nz: int = 3,
    nc: int = 2,
    nt: int = 1,
    image_shape: tuple[int, int] = (128, 128),
    region_id: str = "0",
) -> Path:
    """Create a synthetic OME-TIFF acquisition.

    Each FOV gets one OME-TIFF file with TZCYX axis order.
    """
    path.mkdir(parents=True, exist_ok=True)

    pixel_size_um = 0.325
    step_mm = pixel_size_um * image_shape[1] * 0.85 / 1000
    channel_names = [f"channel_{i}" for i in range(nc)]

    # Write acquisition.yaml (same structure as individual)
    acq_yaml = {
        "acquisition": {
            "experiment_id": "test_ome",
            "start_time": "2026-01-01T00:00:00",
            "widget_type": "wellplate",
        },
        "objective": {
            "name": "20x",
            "magnification": 20.0,
            "pixel_size_um": pixel_size_um,
        },
        "z_stack": {"nz": nz, "delta_z_mm": 0.001, "config": "FROM_BOTTOM", "use_piezo": False},
        "time_series": {"nt": nt, "delta_t_s": 1.0},
        "channels": [
            {
                "name": name,
                "enabled": True,
                "camera_settings": {"exposure_time_ms": 10.0},
                "illumination_settings": {"illumination_channel": f"LED_{i}", "intensity": 50.0},
                "z_offset_um": 0.0,
            }
            for i, name in enumerate(channel_names)
        ],
        "wellplate_scan": {
            "scan_size_mm": nx * step_mm,
            "overlap_percent": 15.0,
            "regions": [
                {"name": region_id, "center_mm": [0.0, 0.0, 0.0], "shape": "Square"}
            ],
        },
    }
    with open(path / "acquisition.yaml", "w") as f:
        yaml.dump(acq_yaml, f, default_flow_style=False)

    with open(path / "acquisition parameters.json", "w") as f:
        json.dump({"sensor_pixel_size_um": 3.45, "tube_lens_mm": 50.0}, f)

    # Write OME-TIFF files
    ome_dir = path / "ome_tiff"
    ome_dir.mkdir()

    fov_idx = 0
    for iy in range(ny):
        for ix in range(nx):
            fname = f"{region_id}_{fov_idx:05}.ome.tiff"
            # Shape: TZCYX
            data = np.random.randint(
                0, 4095, (nt, nz, nc, *image_shape), dtype=np.uint16
            )
            metadata = {
                "axes": "TZCYX",
                "Channel": {"Name": channel_names},
                "PhysicalSizeX": pixel_size_um,
                "PhysicalSizeY": pixel_size_um,
            }
            tifffile.imwrite(
                str(ome_dir / fname),
                data,
                ome=True,
                metadata=metadata,
            )
            fov_idx += 1

    # Write coordinates.csv in timepoint dir
    tp_dir = path / "0"
    tp_dir.mkdir()
    rows = []
    fov_idx = 0
    for iy in range(ny):
        for ix in range(nx):
            for z in range(nz):
                rows.append({
                    "region": region_id,
                    "fov": fov_idx,
                    "z_level": z,
                    "x (mm)": ix * step_mm,
                    "y (mm)": iy * step_mm,
                    "z (um)": z * 1.0,
                    "time": 0.0,
                })
            fov_idx += 1
    with open(tp_dir / "coordinates.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_data_model.py::TestFixtureGenerator -v`
Expected: All PASS

- [ ] **Step 5: Add fixture to conftest.py**

Update `tests/conftest.py`:
```python
"""Shared test fixtures for squid-tools."""

from pathlib import Path

import pytest

from tests.fixtures.generate_fixtures import (
    create_individual_acquisition,
    create_ome_tiff_acquisition,
)


@pytest.fixture
def tmp_acquisition(tmp_path: Path) -> Path:
    """Return a temporary directory for creating test acquisitions."""
    return tmp_path / "test_acquisition"


@pytest.fixture
def individual_acquisition(tmp_path: Path) -> Path:
    """Create a 3x3 individual images acquisition with 2 channels, 2 z-levels."""
    return create_individual_acquisition(
        tmp_path / "individual_acq", nx=3, ny=3, nz=2, nc=2, nt=1
    )


@pytest.fixture
def ome_tiff_acquisition(tmp_path: Path) -> Path:
    """Create a 2x2 OME-TIFF acquisition with 2 channels, 3 z-levels."""
    return create_ome_tiff_acquisition(
        tmp_path / "ome_acq", nx=2, ny=2, nz=3, nc=2, nt=1
    )
```

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/generate_fixtures.py tests/conftest.py tests/unit/test_data_model.py
git commit -m "feat: fixture generator for synthetic Squid acquisitions"
```

---

### Task 4: FormatReader ABC and IndividualImageReader

**Files:**
- Create: `squid_tools/core/readers/base.py`
- Create: `squid_tools/core/readers/individual.py`
- Create: `tests/unit/test_readers.py`
- Modify: `squid_tools/core/readers/__init__.py`

- [ ] **Step 1: Write failing tests for reader ABC and individual reader**

`tests/unit/test_readers.py`:
```python
"""Tests for format readers."""

from pathlib import Path

import numpy as np

from squid_tools.core.data_model import AcquisitionFormat, FrameKey
from squid_tools.core.readers import detect_reader
from squid_tools.core.readers.individual import IndividualImageReader


class TestIndividualImageReader:
    def test_detect_individual_format(self, individual_acquisition: Path) -> None:
        assert IndividualImageReader.detect(individual_acquisition) is True

    def test_detect_rejects_ome_tiff(self, ome_tiff_acquisition: Path) -> None:
        assert IndividualImageReader.detect(ome_tiff_acquisition) is False

    def test_read_metadata_format(self, individual_acquisition: Path) -> None:
        reader = IndividualImageReader()
        acq = reader.read_metadata(individual_acquisition)
        assert acq.format == AcquisitionFormat.INDIVIDUAL_IMAGES

    def test_read_metadata_regions(self, individual_acquisition: Path) -> None:
        reader = IndividualImageReader()
        acq = reader.read_metadata(individual_acquisition)
        assert "0" in acq.regions
        assert len(acq.regions["0"].fovs) == 9  # 3x3 grid

    def test_read_metadata_channels(self, individual_acquisition: Path) -> None:
        reader = IndividualImageReader()
        acq = reader.read_metadata(individual_acquisition)
        assert len(acq.channels) == 2

    def test_read_metadata_objective(self, individual_acquisition: Path) -> None:
        reader = IndividualImageReader()
        acq = reader.read_metadata(individual_acquisition)
        assert acq.objective.pixel_size_um == 0.325
        assert acq.objective.magnification == 20.0

    def test_read_frame(self, individual_acquisition: Path) -> None:
        reader = IndividualImageReader()
        reader.read_metadata(individual_acquisition)
        key = FrameKey(region="0", fov=0, z=0, channel=0, timepoint=0)
        frame = reader.read_frame(key)
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (128, 128)
        assert frame.dtype == np.uint16


class TestDetectReader:
    def test_detect_individual(self, individual_acquisition: Path) -> None:
        reader = detect_reader(individual_acquisition)
        assert isinstance(reader, IndividualImageReader)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_readers.py -v`
Expected: FAIL with import errors

- [ ] **Step 3: Implement FormatReader ABC**

`squid_tools/core/readers/base.py`:
```python
"""Abstract base class for format readers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from squid_tools.core.data_model import Acquisition, FrameKey


class FormatReader(ABC):
    """Base class for all format readers.

    Subclasses implement detection, metadata parsing, and frame loading
    for a specific Squid output format.
    """

    @classmethod
    @abstractmethod
    def detect(cls, path: Path) -> bool:
        """Check if this reader can handle the acquisition at the given path."""
        ...

    @abstractmethod
    def read_metadata(self, path: Path) -> Acquisition:
        """Parse all metadata into the unified Acquisition model."""
        ...

    @abstractmethod
    def read_frame(self, key: FrameKey) -> np.ndarray:
        """Load a single 2D frame identified by the given key."""
        ...
```

- [ ] **Step 4: Implement IndividualImageReader**

`squid_tools/core/readers/individual.py`:
```python
"""Reader for Squid INDIVIDUAL_IMAGES format.

Directory structure:
    acquisition_dir/
    ├── acquisition.yaml
    ├── acquisition parameters.json
    └── {timepoint}/
        ├── coordinates.csv
        └── {region}_{fov}_{z}_{channel_name}.tiff
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import tifffile
import yaml

from squid_tools.core.data_model import (
    Acquisition,
    AcquisitionChannel,
    AcquisitionFormat,
    AcquisitionMode,
    FOVPosition,
    FrameKey,
    ObjectiveMetadata,
    Region,
    ScanConfig,
    TimeSeriesConfig,
    ZStackConfig,
)
from squid_tools.core.readers.base import FormatReader


class IndividualImageReader(FormatReader):
    """Reads Squid INDIVIDUAL_IMAGES acquisitions."""

    def __init__(self) -> None:
        self._path: Path | None = None
        self._acq: Acquisition | None = None
        self._channel_names: list[str] = []

    @classmethod
    def detect(cls, path: Path) -> bool:
        """Detect individual images format.

        Individual images have timepoint directories with .tiff files
        but NO ome_tiff/ directory and NO plate.ome.zarr/.
        """
        if not (path / "acquisition.yaml").exists():
            return False
        if (path / "ome_tiff").exists():
            return False
        if (path / "plate.ome.zarr").exists():
            return False
        # Check for a timepoint directory with tiff files
        tp0 = path / "0"
        if tp0.is_dir() and list(tp0.glob("*.tiff")):
            return True
        return False

    def read_metadata(self, path: Path) -> Acquisition:
        """Parse acquisition.yaml + coordinates.csv into Acquisition model."""
        self._path = path

        with open(path / "acquisition.yaml") as f:
            meta = yaml.safe_load(f)

        # Objective
        obj_meta = meta.get("objective", {})
        objective = ObjectiveMetadata(
            name=obj_meta.get("name", "unknown"),
            magnification=obj_meta.get("magnification", 1.0),
            pixel_size_um=obj_meta.get("pixel_size_um", 1.0),
        )

        # Read acquisition parameters.json for sensor info
        params_file = path / "acquisition parameters.json"
        if params_file.exists():
            with open(params_file) as f:
                params = json.load(f)
            objective.sensor_pixel_size_um = params.get("sensor_pixel_size_um")
            objective.tube_lens_mm = params.get("tube_lens_mm")

        # Channels
        channels: list[AcquisitionChannel] = []
        for ch in meta.get("channels", []):
            illum = ch.get("illumination_settings", {})
            cam = ch.get("camera_settings", {})
            channels.append(AcquisitionChannel(
                name=ch.get("name", ""),
                illumination_source=illum.get("illumination_channel", ""),
                illumination_intensity=illum.get("intensity", 0.0),
                exposure_time_ms=cam.get("exposure_time_ms", 0.0),
                z_offset_um=ch.get("z_offset_um", 0.0),
            ))
        self._channel_names = [ch.name for ch in channels]

        # Mode
        acq_meta = meta.get("acquisition", {})
        widget_type = acq_meta.get("widget_type", "wellplate")
        mode = AcquisitionMode(widget_type) if widget_type in ("wellplate", "flexible") else AcquisitionMode.MANUAL

        # Scan config
        scan = ScanConfig()
        overlap: float | None = None
        if "wellplate_scan" in meta:
            wp = meta["wellplate_scan"]
            overlap = wp.get("overlap_percent")
            scan = ScanConfig(overlap_percent=overlap)
        elif "flexible_scan" in meta:
            fs = meta["flexible_scan"]
            overlap = fs.get("overlap_percent")
            scan = ScanConfig(overlap_percent=overlap)

        # Z-stack
        z_stack = None
        zs_meta = meta.get("z_stack", {})
        if zs_meta.get("nz", 0) > 0:
            z_stack = ZStackConfig(
                nz=zs_meta["nz"],
                delta_z_mm=zs_meta.get("delta_z_mm", 0.001),
                direction="FROM_BOTTOM" if zs_meta.get("config") == "FROM_BOTTOM" else "FROM_TOP",
                use_piezo=zs_meta.get("use_piezo", False),
            )

        # Time series
        time_series = None
        ts_meta = meta.get("time_series", {})
        if ts_meta.get("nt", 0) > 0:
            time_series = TimeSeriesConfig(
                nt=ts_meta["nt"],
                delta_t_s=ts_meta.get("delta_t_s", 1.0),
            )

        # Regions from coordinates.csv
        regions = self._parse_regions(path, meta)

        self._acq = Acquisition(
            path=path,
            format=AcquisitionFormat.INDIVIDUAL_IMAGES,
            mode=mode,
            objective=objective,
            channels=channels,
            scan=scan,
            z_stack=z_stack,
            time_series=time_series,
            regions=regions,
        )
        return self._acq

    def _parse_regions(self, path: Path, meta: dict) -> dict[str, Region]:
        """Parse regions from coordinates.csv and acquisition.yaml."""
        regions: dict[str, Region] = {}

        # Read coordinates from first timepoint
        coords_file = path / "0" / "coordinates.csv"
        if not coords_file.exists():
            return regions

        with open(coords_file) as f:
            reader = csv.DictReader(f)
            for row in reader:
                rid = str(row["region"])
                fov_idx = int(row["fov"])
                if rid not in regions:
                    # Get center from yaml if available
                    center = (0.0, 0.0, 0.0)
                    for scan_key in ("wellplate_scan", "flexible_scan"):
                        scan_meta = meta.get(scan_key, {})
                        for r in scan_meta.get("regions", scan_meta.get("positions", [])):
                            if str(r.get("name")) == rid:
                                c = r.get("center_mm", [0, 0, 0])
                                center = (float(c[0]), float(c[1]), float(c[2]))
                    regions[rid] = Region(region_id=rid, center_mm=center)

                # Add FOV if not already present
                existing_fovs = {f.fov_index for f in regions[rid].fovs}
                if fov_idx not in existing_fovs:
                    regions[rid].fovs.append(FOVPosition(
                        fov_index=fov_idx,
                        x_mm=float(row["x (mm)"]),
                        y_mm=float(row["y (mm)"]),
                        z_um=float(row.get("z (um)", 0)),
                    ))

        return regions

    def read_frame(self, key: FrameKey) -> np.ndarray:
        """Load a single frame from disk."""
        if self._path is None:
            raise RuntimeError("Must call read_metadata before read_frame")

        channel_name = self._channel_names[key.channel]
        fname = f"{key.region}_{key.fov}_{key.z}_{channel_name}.tiff"
        frame_path = self._path / str(key.timepoint) / fname

        return tifffile.imread(str(frame_path))
```

- [ ] **Step 5: Update readers __init__.py with detect_reader**

`squid_tools/core/readers/__init__.py`:
```python
"""Format readers for Squid acquisition data."""

from __future__ import annotations

from pathlib import Path

from squid_tools.core.readers.base import FormatReader
from squid_tools.core.readers.individual import IndividualImageReader


_READERS: list[type[FormatReader]] = [
    IndividualImageReader,
]


def detect_reader(path: Path) -> FormatReader:
    """Auto-detect the format and return the appropriate reader."""
    for reader_cls in _READERS:
        if reader_cls.detect(path):
            return reader_cls()
    raise ValueError(f"No reader found for acquisition at {path}")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_readers.py -v`
Expected: All PASS

- [ ] **Step 7: Run ruff and mypy**

Run: `ruff check squid_tools/core/readers/`
Run: `mypy squid_tools/core/readers/`
Expected: Clean

- [ ] **Step 8: Commit**

```bash
git add squid_tools/core/readers/ tests/unit/test_readers.py
git commit -m "feat: FormatReader ABC and IndividualImageReader"
```

---

### Task 5: OME-TIFF Reader

**Files:**
- Create: `squid_tools/core/readers/ome_tiff.py`
- Modify: `tests/unit/test_readers.py`
- Modify: `squid_tools/core/readers/__init__.py`

- [ ] **Step 1: Write failing tests for OME-TIFF reader**

Add to `tests/unit/test_readers.py`:
```python
from squid_tools.core.readers.ome_tiff import OMETiffReader


class TestOMETiffReader:
    def test_detect_ome_tiff_format(self, ome_tiff_acquisition: Path) -> None:
        assert OMETiffReader.detect(ome_tiff_acquisition) is True

    def test_detect_rejects_individual(self, individual_acquisition: Path) -> None:
        assert OMETiffReader.detect(individual_acquisition) is False

    def test_read_metadata_format(self, ome_tiff_acquisition: Path) -> None:
        reader = OMETiffReader()
        acq = reader.read_metadata(ome_tiff_acquisition)
        assert acq.format == AcquisitionFormat.OME_TIFF

    def test_read_metadata_regions(self, ome_tiff_acquisition: Path) -> None:
        reader = OMETiffReader()
        acq = reader.read_metadata(ome_tiff_acquisition)
        assert "0" in acq.regions
        assert len(acq.regions["0"].fovs) == 4  # 2x2 grid

    def test_read_frame(self, ome_tiff_acquisition: Path) -> None:
        reader = OMETiffReader()
        reader.read_metadata(ome_tiff_acquisition)
        key = FrameKey(region="0", fov=0, z=0, channel=0, timepoint=0)
        frame = reader.read_frame(key)
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (128, 128)
        assert frame.dtype == np.uint16
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_readers.py::TestOMETiffReader -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement OMETiffReader**

`squid_tools/core/readers/ome_tiff.py`:
```python
"""Reader for Squid OME-TIFF format.

Directory structure:
    acquisition_dir/
    ├── acquisition.yaml
    ├── acquisition parameters.json
    ├── ome_tiff/
    │   └── {region}_{fov:05}.ome.tiff  (TZCYX)
    └── {timepoint}/
        └── coordinates.csv
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import tifffile
import yaml

from squid_tools.core.data_model import (
    Acquisition,
    AcquisitionChannel,
    AcquisitionFormat,
    AcquisitionMode,
    FOVPosition,
    FrameKey,
    ObjectiveMetadata,
    Region,
    ScanConfig,
    TimeSeriesConfig,
    ZStackConfig,
)
from squid_tools.core.readers.base import FormatReader


class OMETiffReader(FormatReader):
    """Reads Squid OME-TIFF acquisitions."""

    def __init__(self) -> None:
        self._path: Path | None = None
        self._acq: Acquisition | None = None
        self._fov_files: dict[tuple[str, int], Path] = {}  # (region, fov) -> file path

    @classmethod
    def detect(cls, path: Path) -> bool:
        """Detect OME-TIFF format: has ome_tiff/ directory with .ome.tiff files."""
        if not (path / "acquisition.yaml").exists():
            return False
        ome_dir = path / "ome_tiff"
        if ome_dir.is_dir() and list(ome_dir.glob("*.ome.tiff")):
            return True
        return False

    def read_metadata(self, path: Path) -> Acquisition:
        """Parse acquisition.yaml + OME-TIFF directory structure."""
        self._path = path

        with open(path / "acquisition.yaml") as f:
            meta = yaml.safe_load(f)

        # Objective
        obj_meta = meta.get("objective", {})
        objective = ObjectiveMetadata(
            name=obj_meta.get("name", "unknown"),
            magnification=obj_meta.get("magnification", 1.0),
            pixel_size_um=obj_meta.get("pixel_size_um", 1.0),
        )

        params_file = path / "acquisition parameters.json"
        if params_file.exists():
            with open(params_file) as f:
                params = json.load(f)
            objective.sensor_pixel_size_um = params.get("sensor_pixel_size_um")
            objective.tube_lens_mm = params.get("tube_lens_mm")

        # Channels
        channels: list[AcquisitionChannel] = []
        for ch in meta.get("channels", []):
            illum = ch.get("illumination_settings", {})
            cam = ch.get("camera_settings", {})
            channels.append(AcquisitionChannel(
                name=ch.get("name", ""),
                illumination_source=illum.get("illumination_channel", ""),
                illumination_intensity=illum.get("intensity", 0.0),
                exposure_time_ms=cam.get("exposure_time_ms", 0.0),
                z_offset_um=ch.get("z_offset_um", 0.0),
            ))

        # Mode
        acq_meta = meta.get("acquisition", {})
        widget_type = acq_meta.get("widget_type", "wellplate")
        mode = AcquisitionMode(widget_type) if widget_type in ("wellplate", "flexible") else AcquisitionMode.MANUAL

        # Scan config
        scan = ScanConfig()
        if "wellplate_scan" in meta:
            scan = ScanConfig(overlap_percent=meta["wellplate_scan"].get("overlap_percent"))
        elif "flexible_scan" in meta:
            scan = ScanConfig(overlap_percent=meta["flexible_scan"].get("overlap_percent"))

        # Z-stack
        z_stack = None
        zs_meta = meta.get("z_stack", {})
        if zs_meta.get("nz", 0) > 0:
            z_stack = ZStackConfig(
                nz=zs_meta["nz"],
                delta_z_mm=zs_meta.get("delta_z_mm", 0.001),
                direction="FROM_BOTTOM" if zs_meta.get("config") == "FROM_BOTTOM" else "FROM_TOP",
                use_piezo=zs_meta.get("use_piezo", False),
            )

        # Time series
        time_series = None
        ts_meta = meta.get("time_series", {})
        if ts_meta.get("nt", 0) > 0:
            time_series = TimeSeriesConfig(nt=ts_meta["nt"], delta_t_s=ts_meta.get("delta_t_s", 1.0))

        # Discover OME-TIFF files and build regions
        regions = self._parse_regions_from_files(path, meta)

        self._acq = Acquisition(
            path=path,
            format=AcquisitionFormat.OME_TIFF,
            mode=mode,
            objective=objective,
            channels=channels,
            scan=scan,
            z_stack=z_stack,
            time_series=time_series,
            regions=regions,
        )
        return self._acq

    def _parse_regions_from_files(self, path: Path, meta: dict) -> dict[str, Region]:
        """Build regions from OME-TIFF filenames and coordinates.csv."""
        regions: dict[str, Region] = {}
        ome_dir = path / "ome_tiff"

        # Map files: {region}_{fov:05}.ome.tiff
        for f in sorted(ome_dir.glob("*.ome.tiff")):
            stem = f.stem.replace(".ome", "")
            parts = stem.rsplit("_", 1)
            if len(parts) == 2:
                rid, fov_str = parts
                fov_idx = int(fov_str)
                self._fov_files[(rid, fov_idx)] = f

                if rid not in regions:
                    center = (0.0, 0.0, 0.0)
                    for scan_key in ("wellplate_scan", "flexible_scan"):
                        scan_meta = meta.get(scan_key, {})
                        for r in scan_meta.get("regions", scan_meta.get("positions", [])):
                            if str(r.get("name")) == rid:
                                c = r.get("center_mm", [0, 0, 0])
                                center = (float(c[0]), float(c[1]), float(c[2]))
                    regions[rid] = Region(region_id=rid, center_mm=center)

        # Add FOV positions from coordinates.csv
        coords_file = path / "0" / "coordinates.csv"
        if coords_file.exists():
            with open(coords_file) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rid = str(row["region"])
                    fov_idx = int(row["fov"])
                    if rid in regions:
                        existing = {fv.fov_index for fv in regions[rid].fovs}
                        if fov_idx not in existing:
                            regions[rid].fovs.append(FOVPosition(
                                fov_index=fov_idx,
                                x_mm=float(row["x (mm)"]),
                                y_mm=float(row["y (mm)"]),
                                z_um=float(row.get("z (um)", 0)),
                            ))

        return regions

    def read_frame(self, key: FrameKey) -> np.ndarray:
        """Load a single 2D frame from an OME-TIFF file.

        OME-TIFF axis order is TZCYX. We index [t, z, c, :, :].
        """
        file_key = (key.region, key.fov)
        if file_key not in self._fov_files:
            raise FileNotFoundError(f"No OME-TIFF for region={key.region}, fov={key.fov}")

        fpath = self._fov_files[file_key]
        with tifffile.TiffFile(str(fpath)) as tif:
            data = tif.asarray()
            # data shape: (T, Z, C, Y, X)
            return data[key.timepoint, key.z, key.channel]  # type: ignore[no-any-return]
```

- [ ] **Step 4: Register OMETiffReader in __init__.py**

Update `squid_tools/core/readers/__init__.py`:
```python
"""Format readers for Squid acquisition data."""

from __future__ import annotations

from pathlib import Path

from squid_tools.core.readers.base import FormatReader
from squid_tools.core.readers.individual import IndividualImageReader
from squid_tools.core.readers.ome_tiff import OMETiffReader


_READERS: list[type[FormatReader]] = [
    OMETiffReader,
    IndividualImageReader,
]


def detect_reader(path: Path) -> FormatReader:
    """Auto-detect the format and return the appropriate reader."""
    for reader_cls in _READERS:
        if reader_cls.detect(path):
            return reader_cls()
    raise ValueError(f"No reader found for acquisition at {path}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_readers.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add squid_tools/core/readers/ tests/unit/test_readers.py
git commit -m "feat: OME-TIFF reader with format detection"
```

---

### Task 6: Zarr Reader

**Files:**
- Create: `squid_tools/core/readers/zarr_reader.py`
- Modify: `tests/unit/test_readers.py`
- Modify: `tests/fixtures/generate_fixtures.py`
- Modify: `squid_tools/core/readers/__init__.py`

Note: Zarr support in Squid uses HCS plate format (`plate.ome.zarr/{row}/{col}/{fov}/0` with 5D TZCYX) and non-HCS per-FOV format (`zarr/{region}/fov_{n}.ome.zarr`). For this task we implement HCS mode only, which is the primary Zarr format.

- [ ] **Step 1: Add Zarr fixture generator**

Add to `tests/fixtures/generate_fixtures.py`:
```python
import zarr


def create_zarr_hcs_acquisition(
    path: Path,
    nx: int = 2,
    ny: int = 2,
    nz: int = 3,
    nc: int = 2,
    nt: int = 1,
    image_shape: tuple[int, int] = (128, 128),
    region_id: str = "0",
    row: str = "A",
    col: str = "1",
) -> Path:
    """Create a synthetic Zarr HCS acquisition.

    Structure: plate.ome.zarr/{row}/{col}/{fov}/0 with 5D (T,C,Z,Y,X).
    """
    path.mkdir(parents=True, exist_ok=True)

    pixel_size_um = 0.325
    step_mm = pixel_size_um * image_shape[1] * 0.85 / 1000
    channel_names = [f"channel_{i}" for i in range(nc)]

    # Write acquisition.yaml
    acq_yaml = {
        "acquisition": {
            "experiment_id": "test_zarr",
            "start_time": "2026-01-01T00:00:00",
            "widget_type": "wellplate",
        },
        "objective": {"name": "20x", "magnification": 20.0, "pixel_size_um": pixel_size_um},
        "z_stack": {"nz": nz, "delta_z_mm": 0.001, "config": "FROM_BOTTOM", "use_piezo": False},
        "time_series": {"nt": nt, "delta_t_s": 1.0},
        "channels": [
            {
                "name": name,
                "enabled": True,
                "camera_settings": {"exposure_time_ms": 10.0},
                "illumination_settings": {"illumination_channel": f"LED_{i}", "intensity": 50.0},
                "z_offset_um": 0.0,
            }
            for i, name in enumerate(channel_names)
        ],
        "wellplate_scan": {
            "scan_size_mm": nx * step_mm,
            "overlap_percent": 15.0,
            "regions": [
                {"name": region_id, "center_mm": [0.0, 0.0, 0.0], "shape": "Square"}
            ],
        },
    }
    with open(path / "acquisition.yaml", "w") as f:
        yaml.dump(acq_yaml, f, default_flow_style=False)

    with open(path / "acquisition parameters.json", "w") as f:
        json.dump({"sensor_pixel_size_um": 3.45, "tube_lens_mm": 50.0}, f)

    # Create HCS Zarr store
    plate_path = path / "plate.ome.zarr"
    store = zarr.DirectoryStore(str(plate_path))
    root = zarr.group(store=store, overwrite=True)

    n_fovs = nx * ny
    for fov_idx in range(n_fovs):
        fov_group = root.require_group(f"{row}/{col}/{fov_idx}/0")
        data = np.random.randint(0, 4095, (nt, nc, nz, *image_shape), dtype=np.uint16)
        fov_group.create_dataset("data", data=data, chunks=(1, 1, 1, *image_shape))

    # Write coordinates.csv
    tp_dir = path / "0"
    tp_dir.mkdir()
    rows_list: list[dict[str, object]] = []
    fov_idx = 0
    for iy in range(ny):
        for ix in range(nx):
            for z in range(nz):
                rows_list.append({
                    "region": region_id,
                    "fov": fov_idx,
                    "z_level": z,
                    "x (mm)": ix * step_mm,
                    "y (mm)": iy * step_mm,
                    "z (um)": z * 1.0,
                    "time": 0.0,
                })
            fov_idx += 1
    with open(tp_dir / "coordinates.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows_list[0].keys()))
        writer.writeheader()
        writer.writerows(rows_list)

    return path
```

- [ ] **Step 2: Add Zarr fixture to conftest.py**

Add to `tests/conftest.py`:
```python
from tests.fixtures.generate_fixtures import create_zarr_hcs_acquisition


@pytest.fixture
def zarr_hcs_acquisition(tmp_path: Path) -> Path:
    """Create a 2x2 Zarr HCS acquisition with 2 channels, 3 z-levels."""
    return create_zarr_hcs_acquisition(
        tmp_path / "zarr_acq", nx=2, ny=2, nz=3, nc=2, nt=1
    )
```

- [ ] **Step 3: Write failing tests for ZarrReader**

Add to `tests/unit/test_readers.py`:
```python
from squid_tools.core.readers.zarr_reader import ZarrReader


class TestZarrReader:
    def test_detect_zarr_format(self, zarr_hcs_acquisition: Path) -> None:
        assert ZarrReader.detect(zarr_hcs_acquisition) is True

    def test_detect_rejects_individual(self, individual_acquisition: Path) -> None:
        assert ZarrReader.detect(individual_acquisition) is False

    def test_read_metadata_format(self, zarr_hcs_acquisition: Path) -> None:
        reader = ZarrReader()
        acq = reader.read_metadata(zarr_hcs_acquisition)
        assert acq.format == AcquisitionFormat.ZARR

    def test_read_metadata_regions(self, zarr_hcs_acquisition: Path) -> None:
        reader = ZarrReader()
        acq = reader.read_metadata(zarr_hcs_acquisition)
        assert "0" in acq.regions
        assert len(acq.regions["0"].fovs) == 4  # 2x2 grid

    def test_read_frame(self, zarr_hcs_acquisition: Path) -> None:
        reader = ZarrReader()
        reader.read_metadata(zarr_hcs_acquisition)
        key = FrameKey(region="0", fov=0, z=0, channel=0, timepoint=0)
        frame = reader.read_frame(key)
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (128, 128)
        assert frame.dtype == np.uint16
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/unit/test_readers.py::TestZarrReader -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 5: Implement ZarrReader**

`squid_tools/core/readers/zarr_reader.py`:
```python
"""Reader for Squid Zarr HCS format.

Directory structure:
    acquisition_dir/
    ├── acquisition.yaml
    ├── plate.ome.zarr/
    │   └── {row}/{col}/{fov}/0/data  (5D: T,C,Z,Y,X)
    └── {timepoint}/
        └── coordinates.csv
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import yaml
import zarr

from squid_tools.core.data_model import (
    Acquisition,
    AcquisitionChannel,
    AcquisitionFormat,
    AcquisitionMode,
    FOVPosition,
    FrameKey,
    ObjectiveMetadata,
    Region,
    ScanConfig,
    TimeSeriesConfig,
    ZStackConfig,
)
from squid_tools.core.readers.base import FormatReader


class ZarrReader(FormatReader):
    """Reads Squid Zarr HCS acquisitions."""

    def __init__(self) -> None:
        self._path: Path | None = None
        self._root: zarr.Group | None = None
        self._fov_groups: dict[tuple[str, int], zarr.Group] = {}

    @classmethod
    def detect(cls, path: Path) -> bool:
        """Detect Zarr format: has plate.ome.zarr/ directory."""
        if not (path / "acquisition.yaml").exists():
            return False
        return (path / "plate.ome.zarr").is_dir()

    def read_metadata(self, path: Path) -> Acquisition:
        """Parse acquisition.yaml + Zarr store structure."""
        self._path = path

        with open(path / "acquisition.yaml") as f:
            meta = yaml.safe_load(f)

        obj_meta = meta.get("objective", {})
        objective = ObjectiveMetadata(
            name=obj_meta.get("name", "unknown"),
            magnification=obj_meta.get("magnification", 1.0),
            pixel_size_um=obj_meta.get("pixel_size_um", 1.0),
        )

        params_file = path / "acquisition parameters.json"
        if params_file.exists():
            with open(params_file) as f:
                params = json.load(f)
            objective.sensor_pixel_size_um = params.get("sensor_pixel_size_um")
            objective.tube_lens_mm = params.get("tube_lens_mm")

        channels: list[AcquisitionChannel] = []
        for ch in meta.get("channels", []):
            illum = ch.get("illumination_settings", {})
            cam = ch.get("camera_settings", {})
            channels.append(AcquisitionChannel(
                name=ch.get("name", ""),
                illumination_source=illum.get("illumination_channel", ""),
                illumination_intensity=illum.get("intensity", 0.0),
                exposure_time_ms=cam.get("exposure_time_ms", 0.0),
                z_offset_um=ch.get("z_offset_um", 0.0),
            ))

        acq_meta = meta.get("acquisition", {})
        widget_type = acq_meta.get("widget_type", "wellplate")
        mode = AcquisitionMode(widget_type) if widget_type in ("wellplate", "flexible") else AcquisitionMode.MANUAL

        scan = ScanConfig()
        if "wellplate_scan" in meta:
            scan = ScanConfig(overlap_percent=meta["wellplate_scan"].get("overlap_percent"))

        z_stack = None
        zs_meta = meta.get("z_stack", {})
        if zs_meta.get("nz", 0) > 0:
            z_stack = ZStackConfig(
                nz=zs_meta["nz"],
                delta_z_mm=zs_meta.get("delta_z_mm", 0.001),
                direction="FROM_BOTTOM" if zs_meta.get("config") == "FROM_BOTTOM" else "FROM_TOP",
                use_piezo=zs_meta.get("use_piezo", False),
            )

        time_series = None
        ts_meta = meta.get("time_series", {})
        if ts_meta.get("nt", 0) > 0:
            time_series = TimeSeriesConfig(nt=ts_meta["nt"], delta_t_s=ts_meta.get("delta_t_s", 1.0))

        # Open Zarr store and discover FOVs
        plate_path = path / "plate.ome.zarr"
        store = zarr.DirectoryStore(str(plate_path))
        self._root = zarr.open_group(store=store, mode="r")

        regions = self._parse_regions(path, meta)

        return Acquisition(
            path=path,
            format=AcquisitionFormat.ZARR,
            mode=mode,
            objective=objective,
            channels=channels,
            scan=scan,
            z_stack=z_stack,
            time_series=time_series,
            regions=regions,
        )

    def _parse_regions(self, path: Path, meta: dict) -> dict[str, Region]:
        """Build regions from coordinates.csv and Zarr store structure."""
        regions: dict[str, Region] = {}

        # Discover FOV groups in the Zarr store
        if self._root is not None:
            for row_name in sorted(self._root.group_keys()):
                row_group = self._root[row_name]
                for col_name in sorted(row_group.group_keys()):
                    col_group = row_group[col_name]
                    for fov_name in sorted(col_group.group_keys()):
                        fov_group = col_group[fov_name]
                        if "0" in fov_group:
                            fov_idx = int(fov_name)
                            self._fov_groups[("0", fov_idx)] = fov_group["0"]

        # Read positions from coordinates.csv
        coords_file = path / "0" / "coordinates.csv"
        if coords_file.exists():
            with open(coords_file) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rid = str(row["region"])
                    fov_idx = int(row["fov"])
                    if rid not in regions:
                        center = (0.0, 0.0, 0.0)
                        for r in meta.get("wellplate_scan", {}).get("regions", []):
                            if str(r.get("name")) == rid:
                                c = r.get("center_mm", [0, 0, 0])
                                center = (float(c[0]), float(c[1]), float(c[2]))
                        regions[rid] = Region(region_id=rid, center_mm=center)

                    existing = {fv.fov_index for fv in regions[rid].fovs}
                    if fov_idx not in existing:
                        regions[rid].fovs.append(FOVPosition(
                            fov_index=fov_idx,
                            x_mm=float(row["x (mm)"]),
                            y_mm=float(row["y (mm)"]),
                            z_um=float(row.get("z (um)", 0)),
                        ))

        return regions

    def read_frame(self, key: FrameKey) -> np.ndarray:
        """Load a single 2D frame from the Zarr store.

        Zarr HCS data shape: (T, C, Z, Y, X).
        """
        fov_key = (key.region, key.fov)
        if fov_key not in self._fov_groups:
            raise FileNotFoundError(f"No Zarr data for region={key.region}, fov={key.fov}")

        group = self._fov_groups[fov_key]
        data = group["data"]
        return np.array(data[key.timepoint, key.channel, key.z])
```

- [ ] **Step 6: Register ZarrReader in __init__.py**

Update `squid_tools/core/readers/__init__.py`:
```python
"""Format readers for Squid acquisition data."""

from __future__ import annotations

from pathlib import Path

from squid_tools.core.readers.base import FormatReader
from squid_tools.core.readers.individual import IndividualImageReader
from squid_tools.core.readers.ome_tiff import OMETiffReader
from squid_tools.core.readers.zarr_reader import ZarrReader


_READERS: list[type[FormatReader]] = [
    ZarrReader,
    OMETiffReader,
    IndividualImageReader,
]


def detect_reader(path: Path) -> FormatReader:
    """Auto-detect the format and return the appropriate reader."""
    for reader_cls in _READERS:
        if reader_cls.detect(path):
            return reader_cls()
    raise ValueError(f"No reader found for acquisition at {path}")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/unit/test_readers.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add squid_tools/core/readers/ tests/unit/test_readers.py tests/fixtures/generate_fixtures.py tests/conftest.py
git commit -m "feat: Zarr HCS reader with format detection"
```

---

### Task 7: Memory-Bounded LRU Cache

**Files:**
- Create: `squid_tools/core/cache.py`
- Create: `tests/unit/test_cache.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_cache.py`:
```python
"""Tests for memory-bounded LRU cache."""

import numpy as np

from squid_tools.core.cache import MemoryBoundedLRUCache


class TestMemoryBoundedLRUCache:
    def test_get_set(self) -> None:
        cache: MemoryBoundedLRUCache = MemoryBoundedLRUCache(max_bytes=1024 * 1024)
        arr = np.zeros((10, 10), dtype=np.uint16)
        cache.put("key1", arr)
        result = cache.get("key1")
        assert result is not None
        assert np.array_equal(result, arr)

    def test_miss_returns_none(self) -> None:
        cache: MemoryBoundedLRUCache = MemoryBoundedLRUCache(max_bytes=1024 * 1024)
        assert cache.get("missing") is None

    def test_evicts_lru_when_full(self) -> None:
        # Cache fits ~2 arrays of 100 bytes each
        cache: MemoryBoundedLRUCache = MemoryBoundedLRUCache(max_bytes=250)
        a1 = np.zeros(100, dtype=np.uint8)  # 100 bytes
        a2 = np.zeros(100, dtype=np.uint8)  # 100 bytes
        a3 = np.zeros(100, dtype=np.uint8)  # 100 bytes

        cache.put("a1", a1)
        cache.put("a2", a2)
        cache.put("a3", a3)  # should evict a1

        assert cache.get("a1") is None
        assert cache.get("a2") is not None
        assert cache.get("a3") is not None

    def test_rejects_oversized_item(self) -> None:
        cache: MemoryBoundedLRUCache = MemoryBoundedLRUCache(max_bytes=50)
        big = np.zeros(100, dtype=np.uint8)  # 100 bytes > 50
        cache.put("big", big)
        assert cache.get("big") is None

    def test_access_updates_recency(self) -> None:
        cache: MemoryBoundedLRUCache = MemoryBoundedLRUCache(max_bytes=250)
        a1 = np.zeros(100, dtype=np.uint8)
        a2 = np.zeros(100, dtype=np.uint8)
        a3 = np.zeros(100, dtype=np.uint8)

        cache.put("a1", a1)
        cache.put("a2", a2)
        cache.get("a1")  # touch a1, making a2 the LRU
        cache.put("a3", a3)  # should evict a2, not a1

        assert cache.get("a1") is not None
        assert cache.get("a2") is None
        assert cache.get("a3") is not None

    def test_current_bytes(self) -> None:
        cache: MemoryBoundedLRUCache = MemoryBoundedLRUCache(max_bytes=1024)
        arr = np.zeros(100, dtype=np.uint8)
        cache.put("k", arr)
        assert cache.current_bytes == 100

    def test_thread_safety(self) -> None:
        """Basic thread safety: concurrent puts don't crash."""
        import threading

        cache: MemoryBoundedLRUCache = MemoryBoundedLRUCache(max_bytes=10000)

        def writer(prefix: str) -> None:
            for i in range(50):
                cache.put(f"{prefix}_{i}", np.zeros(10, dtype=np.uint8))

        threads = [threading.Thread(target=writer, args=(f"t{i}",)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should not crash; cache should have some entries
        assert cache.current_bytes > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cache.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement MemoryBoundedLRUCache**

`squid_tools/core/cache.py`:
```python
"""Memory-bounded LRU cache for numpy arrays.

Evicts by nbytes (not item count) to bound actual RAM usage.
Pattern from ndviewer_light, proven in production.
"""

from __future__ import annotations

import threading
from collections import OrderedDict

import numpy as np


class MemoryBoundedLRUCache:
    """Thread-safe LRU cache bounded by total memory in bytes.

    Items larger than max_bytes are silently rejected (not cached).
    """

    def __init__(self, max_bytes: int = 256 * 1024 * 1024) -> None:
        self._max_bytes = max_bytes
        self._current_bytes = 0
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def current_bytes(self) -> int:
        return self._current_bytes

    def get(self, key: str) -> np.ndarray | None:
        """Get item from cache. Returns None on miss. Updates recency on hit."""
        with self._lock:
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return self._cache[key]

    def put(self, key: str, value: np.ndarray) -> None:
        """Add item to cache. Evicts LRU entries if over budget.

        Items larger than max_bytes are silently rejected.
        """
        item_bytes = value.nbytes
        if item_bytes > self._max_bytes:
            return

        with self._lock:
            # Remove existing entry if updating
            if key in self._cache:
                self._current_bytes -= self._cache[key].nbytes
                del self._cache[key]

            # Evict LRU entries until there's room
            while self._current_bytes + item_bytes > self._max_bytes and self._cache:
                _, evicted = self._cache.popitem(last=False)
                self._current_bytes -= evicted.nbytes

            self._cache[key] = value
            self._current_bytes += item_bytes

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._current_bytes = 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_cache.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add squid_tools/core/cache.py tests/unit/test_cache.py
git commit -m "feat: memory-bounded LRU cache (ndviewer_light pattern)"
```

---

### Task 8: TiffFile Handle Pool

**Files:**
- Create: `squid_tools/core/handle_pool.py`
- Create: `tests/unit/test_handle_pool.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_handle_pool.py`:
```python
"""Tests for TiffFile handle pool."""

from pathlib import Path

import numpy as np
import tifffile

from squid_tools.core.handle_pool import TiffFileHandlePool


def _create_test_tiff(path: Path) -> Path:
    """Create a minimal TIFF file for testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.zeros((64, 64), dtype=np.uint16)
    tifffile.imwrite(str(path), data)
    return path


class TestTiffFileHandlePool:
    def test_open_and_read(self, tmp_path: Path) -> None:
        pool = TiffFileHandlePool(max_handles=4)
        tiff_path = _create_test_tiff(tmp_path / "test.tiff")
        handle, lock = pool.get(tiff_path)
        with lock:
            data = handle.asarray()
        assert data.shape == (64, 64)

    def test_reuses_handle(self, tmp_path: Path) -> None:
        pool = TiffFileHandlePool(max_handles=4)
        tiff_path = _create_test_tiff(tmp_path / "test.tiff")
        h1, _ = pool.get(tiff_path)
        h2, _ = pool.get(tiff_path)
        assert h1 is h2

    def test_evicts_lru_handle(self, tmp_path: Path) -> None:
        pool = TiffFileHandlePool(max_handles=2)
        p1 = _create_test_tiff(tmp_path / "a.tiff")
        p2 = _create_test_tiff(tmp_path / "b.tiff")
        p3 = _create_test_tiff(tmp_path / "c.tiff")

        pool.get(p1)
        pool.get(p2)
        pool.get(p3)  # should evict p1

        assert pool.handle_count == 2

    def test_close_all(self, tmp_path: Path) -> None:
        pool = TiffFileHandlePool(max_handles=4)
        p1 = _create_test_tiff(tmp_path / "a.tiff")
        pool.get(p1)
        pool.close_all()
        assert pool.handle_count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_handle_pool.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement TiffFileHandlePool**

`squid_tools/core/handle_pool.py`:
```python
"""TiffFile handle pool with LRU eviction.

Keeps up to max_handles open TiffFile objects to avoid
re-parsing IFD chains on repeated reads. Per-file locks
enable parallel reads across files while serializing
same-file reads.

Pattern from ndviewer_light, proven in production.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

import tifffile


class TiffFileHandlePool:
    """Pool of open TiffFile handles with LRU eviction."""

    def __init__(self, max_handles: int = 128) -> None:
        self._max_handles = max_handles
        self._handles: OrderedDict[Path, tuple[tifffile.TiffFile, threading.Lock]] = OrderedDict()
        self._global_lock = threading.Lock()

    @property
    def handle_count(self) -> int:
        return len(self._handles)

    def get(self, path: Path) -> tuple[tifffile.TiffFile, threading.Lock]:
        """Get or open a TiffFile handle for the given path.

        Returns (TiffFile, per-file Lock). Caller must acquire the
        per-file lock before reading from the handle.
        """
        resolved = path.resolve()
        with self._global_lock:
            if resolved in self._handles:
                self._handles.move_to_end(resolved)
                return self._handles[resolved]

            # Evict LRU handles if at capacity
            to_close: list[tifffile.TiffFile] = []
            while len(self._handles) >= self._max_handles:
                _, (evicted_handle, _) = self._handles.popitem(last=False)
                to_close.append(evicted_handle)

        # Close evicted handles outside the global lock
        for h in to_close:
            h.close()

        handle = tifffile.TiffFile(str(resolved))
        lock = threading.Lock()

        with self._global_lock:
            self._handles[resolved] = (handle, lock)

        return handle, lock

    def close_all(self) -> None:
        """Close all open handles."""
        with self._global_lock:
            for handle, _ in self._handles.values():
                handle.close()
            self._handles.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_handle_pool.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add squid_tools/core/handle_pool.py tests/unit/test_handle_pool.py
git commit -m "feat: TiffFile handle pool with LRU eviction"
```

---

### Task 9: Plugin ABC

**Files:**
- Create: `squid_tools/plugins/base.py`
- Create: `tests/unit/test_registry.py`

- [ ] **Step 1: Write failing tests for plugin ABC**

`tests/unit/test_registry.py`:
```python
"""Tests for plugin ABC and registry."""

import numpy as np
from pydantic import BaseModel

from squid_tools.core.data_model import Acquisition, AcquisitionFormat, AcquisitionMode, ObjectiveMetadata, OpticalMetadata
from squid_tools.plugins.base import ProcessingPlugin


class DummyParams(BaseModel):
    sigma: float = 1.0


class DummyPlugin(ProcessingPlugin):
    name = "Dummy"
    category = "correction"
    requires_gpu = False

    def parameters(self) -> type[BaseModel]:
        return DummyParams

    def validate(self, acq: Acquisition) -> list[str]:
        return []

    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        return frames

    def default_params(self, optical: OpticalMetadata) -> BaseModel:
        return DummyParams()

    def test_cases(self) -> list[dict]:
        return [{"input": np.ones((10, 10)), "expected": np.ones((10, 10))}]


class TestProcessingPlugin:
    def test_instantiate_plugin(self) -> None:
        plugin = DummyPlugin()
        assert plugin.name == "Dummy"
        assert plugin.category == "correction"
        assert plugin.requires_gpu is False

    def test_parameters_returns_model_class(self) -> None:
        plugin = DummyPlugin()
        assert plugin.parameters() is DummyParams

    def test_validate_returns_list(self) -> None:
        plugin = DummyPlugin()
        acq = Acquisition(
            path="/tmp/test",
            format=AcquisitionFormat.INDIVIDUAL_IMAGES,
            mode=AcquisitionMode.WELLPLATE,
            objective=ObjectiveMetadata(name="20x", magnification=20.0, pixel_size_um=0.325),
        )
        warnings = plugin.validate(acq)
        assert isinstance(warnings, list)

    def test_process_returns_array(self) -> None:
        plugin = DummyPlugin()
        arr = np.ones((10, 10), dtype=np.uint16)
        result = plugin.process(arr, DummyParams())
        assert isinstance(result, np.ndarray)

    def test_default_params(self) -> None:
        plugin = DummyPlugin()
        params = plugin.default_params(OpticalMetadata())
        assert isinstance(params, DummyParams)

    def test_test_cases_returns_list(self) -> None:
        plugin = DummyPlugin()
        cases = plugin.test_cases()
        assert len(cases) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement ProcessingPlugin ABC**

`squid_tools/plugins/base.py`:
```python
"""Processing plugin abstract base class.

Every processing module implements this interface. Wrapping a new
algorithm = one file, one class, ~50 lines.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import BaseModel

if TYPE_CHECKING:
    from squid_tools.core.data_model import Acquisition, OpticalMetadata


class ProcessingPlugin(ABC):
    """Base class for all processing plugins.

    Attributes:
        name: Human-readable plugin name.
        category: Plugin category ("stitching", "deconvolution", "correction", "phase").
        requires_gpu: Whether GPU is required (with CPU fallback).
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
        """Validate that this plugin can process the given acquisition.

        Returns list of warning/error messages. Empty list = valid.
        """
        ...

    @abstractmethod
    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        """Process frames. Input and output are numpy arrays."""
        ...

    @abstractmethod
    def default_params(self, optical: OpticalMetadata) -> BaseModel:
        """Return default parameters populated from optical metadata."""
        ...

    @abstractmethod
    def test_cases(self) -> list[dict[str, Any]]:
        """Return synthetic test cases: list of {input, expected} dicts."""
        ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_registry.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add squid_tools/plugins/base.py tests/unit/test_registry.py
git commit -m "feat: ProcessingPlugin ABC"
```

---

### Task 10: Pipeline

**Files:**
- Create: `squid_tools/core/pipeline.py`
- Create: `tests/unit/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_pipeline.py`:
```python
"""Tests for processing pipeline."""

import numpy as np
from pydantic import BaseModel

from squid_tools.core.data_model import Acquisition, AcquisitionFormat, AcquisitionMode, ObjectiveMetadata, OpticalMetadata
from squid_tools.core.pipeline import Pipeline
from squid_tools.plugins.base import ProcessingPlugin


class AddOneParams(BaseModel):
    value: int = 1


class AddOnePlugin(ProcessingPlugin):
    name = "AddOne"
    category = "correction"

    def parameters(self) -> type[BaseModel]:
        return AddOneParams

    def validate(self, acq: Acquisition) -> list[str]:
        return []

    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        assert isinstance(params, AddOneParams)
        return frames + params.value

    def default_params(self, optical: OpticalMetadata) -> BaseModel:
        return AddOneParams()

    def test_cases(self) -> list[dict]:
        return []


class MultiplyParams(BaseModel):
    factor: int = 2


class MultiplyPlugin(ProcessingPlugin):
    name = "Multiply"
    category = "correction"

    def parameters(self) -> type[BaseModel]:
        return MultiplyParams

    def validate(self, acq: Acquisition) -> list[str]:
        return []

    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        assert isinstance(params, MultiplyParams)
        return frames * params.factor

    def default_params(self, optical: OpticalMetadata) -> BaseModel:
        return MultiplyParams()

    def test_cases(self) -> list[dict]:
        return []


class TestPipeline:
    def test_empty_pipeline(self) -> None:
        pipe = Pipeline()
        arr = np.ones((10, 10), dtype=np.uint16)
        result = pipe.run(arr)
        assert np.array_equal(result, arr)

    def test_single_step(self) -> None:
        pipe = Pipeline()
        pipe.add(AddOnePlugin(), AddOneParams(value=5))
        arr = np.zeros((10, 10), dtype=np.int32)
        result = pipe.run(arr)
        assert np.all(result == 5)

    def test_chained_steps(self) -> None:
        pipe = Pipeline()
        pipe.add(AddOnePlugin(), AddOneParams(value=3))
        pipe.add(MultiplyPlugin(), MultiplyParams(factor=2))
        arr = np.ones((10, 10), dtype=np.int32)
        result = pipe.run(arr)
        # (1 + 3) * 2 = 8
        assert np.all(result == 8)

    def test_clear(self) -> None:
        pipe = Pipeline()
        pipe.add(AddOnePlugin(), AddOneParams(value=1))
        pipe.clear()
        arr = np.ones((10, 10), dtype=np.int32)
        result = pipe.run(arr)
        assert np.all(result == 1)

    def test_step_count(self) -> None:
        pipe = Pipeline()
        assert len(pipe) == 0
        pipe.add(AddOnePlugin(), AddOneParams())
        assert len(pipe) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement Pipeline**

`squid_tools/core/pipeline.py`:
```python
"""Processing pipeline: chains plugin operations sequentially."""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel

from squid_tools.plugins.base import ProcessingPlugin


class Pipeline:
    """Chains processing plugins and applies them sequentially to frames."""

    def __init__(self) -> None:
        self._steps: list[tuple[ProcessingPlugin, BaseModel]] = []

    def add(self, plugin: ProcessingPlugin, params: BaseModel) -> None:
        """Add a processing step to the pipeline."""
        self._steps.append((plugin, params))

    def run(self, frames: np.ndarray) -> np.ndarray:
        """Run all pipeline steps on the given frames."""
        result = frames
        for plugin, params in self._steps:
            result = plugin.process(result, params)
        return result

    def clear(self) -> None:
        """Remove all steps from the pipeline."""
        self._steps.clear()

    def __len__(self) -> int:
        return len(self._steps)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_pipeline.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add squid_tools/core/pipeline.py tests/unit/test_pipeline.py
git commit -m "feat: processing pipeline with chained plugin steps"
```

---

### Task 11: OME Sidecar

**Files:**
- Create: `squid_tools/core/sidecar.py`
- Create: `tests/unit/test_sidecar.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_sidecar.py`:
```python
"""Tests for OME sidecar manifest."""

import json
from pathlib import Path

from squid_tools.core.sidecar import SidecarManifest, ProcessingRun


class TestSidecarManifest:
    def test_create_empty_manifest(self, tmp_path: Path) -> None:
        manifest = SidecarManifest(acquisition_path=tmp_path)
        assert len(manifest.runs) == 0

    def test_add_run(self, tmp_path: Path) -> None:
        manifest = SidecarManifest(acquisition_path=tmp_path)
        run = ProcessingRun(
            plugin="TileFusion Stitcher",
            version="0.3.1",
            params={"overlap_percent": 15},
            output_path="stitcher/",
        )
        manifest.add_run(run)
        assert len(manifest.runs) == 1
        assert manifest.runs[0].plugin == "TileFusion Stitcher"

    def test_save_and_load(self, tmp_path: Path) -> None:
        manifest = SidecarManifest(acquisition_path=tmp_path)
        manifest.add_run(ProcessingRun(
            plugin="TestPlugin",
            version="1.0",
            params={"key": "value"},
            output_path="test/",
        ))
        manifest.save()

        # Verify file exists
        manifest_path = tmp_path / ".squid-tools" / "manifest.json"
        assert manifest_path.exists()

        # Load and verify
        loaded = SidecarManifest.load(tmp_path)
        assert len(loaded.runs) == 1
        assert loaded.runs[0].plugin == "TestPlugin"

    def test_sidecar_dir_created(self, tmp_path: Path) -> None:
        manifest = SidecarManifest(acquisition_path=tmp_path)
        manifest.save()
        assert (tmp_path / ".squid-tools").is_dir()

    def test_plugin_output_dir(self, tmp_path: Path) -> None:
        manifest = SidecarManifest(acquisition_path=tmp_path)
        out_dir = manifest.plugin_output_dir("stitcher")
        assert out_dir == tmp_path / ".squid-tools" / "stitcher"
        assert out_dir.is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_sidecar.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement SidecarManifest**

`squid_tools/core/sidecar.py`:
```python
"""OME sidecar: non-destructive output alongside Squid acquisitions.

Processing results are stored in .squid-tools/ within the acquisition
directory. Original files are never modified. The manifest.json tracks
what was run, when, and with what parameters.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ProcessingRun(BaseModel):
    """Record of a single processing operation."""

    plugin: str
    version: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    params: dict[str, Any] = {}
    input_hash: str | None = None
    output_path: str = ""


class SidecarManifest(BaseModel):
    """Manifest tracking all processing runs for an acquisition."""

    acquisition_path: Path
    runs: list[ProcessingRun] = []

    model_config = {"arbitrary_types_allowed": True}

    def add_run(self, run: ProcessingRun) -> None:
        """Record a processing run."""
        self.runs.append(run)

    def save(self) -> None:
        """Write manifest to .squid-tools/manifest.json."""
        sidecar_dir = self.acquisition_path / ".squid-tools"
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = sidecar_dir / "manifest.json"

        data = {
            "runs": [run.model_dump() for run in self.runs],
        }
        with open(manifest_path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, acquisition_path: Path) -> SidecarManifest:
        """Load manifest from .squid-tools/manifest.json."""
        manifest_path = acquisition_path / ".squid-tools" / "manifest.json"
        manifest = cls(acquisition_path=acquisition_path)

        if manifest_path.exists():
            with open(manifest_path) as f:
                data = json.load(f)
            manifest.runs = [ProcessingRun(**r) for r in data.get("runs", [])]

        return manifest

    def plugin_output_dir(self, plugin_name: str) -> Path:
        """Get or create the output directory for a plugin."""
        out_dir = self.acquisition_path / ".squid-tools" / plugin_name
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_sidecar.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add squid_tools/core/sidecar.py tests/unit/test_sidecar.py
git commit -m "feat: OME sidecar manifest for non-destructive output"
```

---

### Task 12: Plugin Registry

**Files:**
- Create: `squid_tools/core/registry.py`
- Modify: `tests/unit/test_registry.py`

- [ ] **Step 1: Write failing tests for registry**

Add to `tests/unit/test_registry.py`:
```python
from squid_tools.core.registry import PluginRegistry


class TestPluginRegistry:
    def test_register_and_get(self) -> None:
        registry = PluginRegistry()
        plugin = DummyPlugin()
        registry.register(plugin)
        assert registry.get("Dummy") is plugin

    def test_get_missing_returns_none(self) -> None:
        registry = PluginRegistry()
        assert registry.get("missing") is None

    def test_list_plugins(self) -> None:
        registry = PluginRegistry()
        registry.register(DummyPlugin())
        names = registry.list_names()
        assert "Dummy" in names

    def test_list_by_category(self) -> None:
        registry = PluginRegistry()
        registry.register(DummyPlugin())
        correction_plugins = registry.list_by_category("correction")
        assert len(correction_plugins) == 1
        assert correction_plugins[0].name == "Dummy"

    def test_list_empty_category(self) -> None:
        registry = PluginRegistry()
        registry.register(DummyPlugin())
        assert registry.list_by_category("stitching") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_registry.py::TestPluginRegistry -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement PluginRegistry**

`squid_tools/core/registry.py`:
```python
"""Plugin discovery and registration."""

from __future__ import annotations

from squid_tools.plugins.base import ProcessingPlugin


class PluginRegistry:
    """Registry of available processing plugins."""

    def __init__(self) -> None:
        self._plugins: dict[str, ProcessingPlugin] = {}

    def register(self, plugin: ProcessingPlugin) -> None:
        """Register a plugin by its name."""
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> ProcessingPlugin | None:
        """Get a plugin by name. Returns None if not found."""
        return self._plugins.get(name)

    def list_names(self) -> list[str]:
        """List all registered plugin names."""
        return list(self._plugins.keys())

    def list_by_category(self, category: str) -> list[ProcessingPlugin]:
        """List plugins matching the given category."""
        return [p for p in self._plugins.values() if p.category == category]

    def list_all(self) -> list[ProcessingPlugin]:
        """List all registered plugins."""
        return list(self._plugins.values())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_registry.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS

Run: `ruff check squid_tools/`
Expected: Clean

- [ ] **Step 6: Commit**

```bash
git add squid_tools/core/registry.py tests/unit/test_registry.py
git commit -m "feat: plugin registry for discovery and lookup"
```

---

### Task 13: Final Verification

- [ ] **Step 1: Run full test suite with coverage**

Run: `pytest -v --tb=short`
Expected: All tests PASS (should be ~30+ tests across all files)

- [ ] **Step 2: Run linting and type checking**

Run: `ruff check squid_tools/ tests/`
Expected: Clean

Run: `mypy squid_tools/`
Expected: Clean (or only known pydantic/dask stubs issues)

- [ ] **Step 3: Verify package installs cleanly**

Run: `pip install -e ".[dev]" && python -c "from squid_tools.core.data_model import Acquisition; print('OK')"`
Expected: Prints `OK`

- [ ] **Step 4: Commit any final fixes and tag**

```bash
git add -A
git commit -m "chore: final verification, all tests passing"
```
