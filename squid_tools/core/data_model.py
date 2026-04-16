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
    tube_lens_mm: float | None = None
    camera_binning: int = 1

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
