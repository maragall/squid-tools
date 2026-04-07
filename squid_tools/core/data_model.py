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
