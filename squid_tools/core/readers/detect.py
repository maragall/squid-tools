"""Format detection and acquisition parsing for Squid datasets."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from squid_tools.core.data_model import (
    Acquisition,
    AcquisitionChannel,
    AcquisitionFormat,
    AcquisitionMode,
    FOVPosition,
    GridParams,
    ObjectiveMetadata,
    OpticalMetadata,
    Region,
    ScanConfig,
    TimeSeriesConfig,
    ZStackConfig,
)

# ---------------------------------------------------------------------------
# Immersion refractive-index defaults
# ---------------------------------------------------------------------------

IMMERSION_RI: dict[str, float] = {
    "air": 1.0,
    "water": 1.333,
    "oil": 1.515,
    "glycerol": 1.473,
    "silicone": 1.406,
}


# ---------------------------------------------------------------------------
# detect_format
# ---------------------------------------------------------------------------

def detect_format(path: Path) -> AcquisitionFormat:
    """Inspect *path* contents and return the :class:`AcquisitionFormat`.

    Detection rules (in priority order):

    1. ``ome_tiff/`` subdirectory  → :attr:`AcquisitionFormat.OME_TIFF`
    2. ``plate.ome.zarr`` or ``zarr/`` subdirectory → :attr:`AcquisitionFormat.ZARR`
    3. Timepoint subdirectories (``00000/``, ``00001/``, …) containing TIFF
       files → :attr:`AcquisitionFormat.INDIVIDUAL_IMAGES`
    """
    path = Path(path)

    if (path / "ome_tiff").is_dir():
        return AcquisitionFormat.OME_TIFF

    if (path / "plate.ome.zarr").exists() or (path / "zarr").is_dir():
        return AcquisitionFormat.ZARR

    # Look for timepoint directories (integer names, zero-padded or not)
    for child in sorted(path.iterdir()):
        if child.is_dir() and child.name.isdigit():
            tiffs = list(child.glob("*.tiff")) + list(child.glob("*.tif"))
            if tiffs:
                return AcquisitionFormat.INDIVIDUAL_IMAGES

    # Default fallback – treat as individual images if timepoint dirs exist
    return AcquisitionFormat.INDIVIDUAL_IMAGES


# ---------------------------------------------------------------------------
# open_acquisition
# ---------------------------------------------------------------------------

def _find_timepoint_dir(path: Path) -> Path | None:
    """Return the first integer-named subdirectory containing TIFFs, or None."""
    for child in sorted(path.iterdir()):
        if child.is_dir() and child.name.isdigit():
            tiffs = list(child.glob("*.tiff")) + list(child.glob("*.tif"))
            if tiffs:
                return child
    return None


# Regex for real Squid naming: {region}_{fov}_{z}_Fluorescence_{wavelength}_nm_Ex.tiff
_SQUID_REAL_RE = re.compile(
    r"^(.+?)_(\d+)_(\d+)_Fluorescence_(\d+)_nm_Ex\.tiff?$"
)


def _detect_channel_wavelengths(timepoint_dir: Path) -> list[str]:
    """Scan a timepoint directory and return sorted list of wavelength strings.

    Looks for filenames matching the real Squid naming convention:
    ``{region}_{fov}_{z}_Fluorescence_{wavelength}_nm_Ex.tiff``

    Returns an empty list if no files match (i.e. old naming convention).
    """
    wavelengths: set[str] = set()
    for f in timepoint_dir.iterdir():
        m = _SQUID_REAL_RE.match(f.name)
        if m:
            wavelengths.add(m.group(4))
    return sorted(wavelengths, key=int) if wavelengths else []


def _open_acquisition_from_params_json(path: Path) -> Acquisition:
    """Parse acquisition when only ``acquisition parameters.json`` exists (no yaml).

    This is the path for real Squid acquisition data that uses the native
    Squid naming convention.
    """
    params_path = path / "acquisition parameters.json"
    with open(params_path) as f:
        hw_params: dict[str, Any] = json.load(f)

    # ------------------------------------------------------------------
    # Objective
    # ------------------------------------------------------------------
    obj_raw: dict[str, Any] = hw_params.get("objective", {})
    tube_lens_mm: float = float(hw_params.get("tube_lens_mm", 180.0))
    sensor_pixel_size_um: float = float(
        hw_params.get("sensor_pixel_size_um", obj_raw.get("sensor_pixel_size_um", 1.85))
    )

    objective = ObjectiveMetadata(
        name=str(obj_raw.get("name", "")),
        magnification=float(obj_raw.get("magnification", 1.0)),
        numerical_aperture=float(obj_raw.get("NA", 0.0)),
        tube_lens_f_mm=float(obj_raw.get("tube_lens_f_mm", 180.0)),
        sensor_pixel_size_um=sensor_pixel_size_um,
        camera_binning=1,
        tube_lens_mm=tube_lens_mm,
    )

    # ------------------------------------------------------------------
    # Optical metadata
    # ------------------------------------------------------------------
    optical = OpticalMetadata(
        modality="widefield",
        immersion_medium="air",
        immersion_ri=IMMERSION_RI["air"],
        numerical_aperture=objective.numerical_aperture,
        pixel_size_um=objective.pixel_size_um,
    )

    # ------------------------------------------------------------------
    # Channels – auto-detect from filenames in first timepoint dir
    # ------------------------------------------------------------------
    tp_dir = _find_timepoint_dir(path)
    wavelengths: list[str] = []
    if tp_dir is not None:
        wavelengths = _detect_channel_wavelengths(tp_dir)

    channels: list[AcquisitionChannel] = [
        AcquisitionChannel(
            name=f"Fluorescence_{wl}_nm_Ex",
            illumination_source=f"{wl} nm",
            illumination_intensity=0.0,
            exposure_time_ms=0.0,
            emission_wavelength_nm=float(wl),
            z_offset_um=0.0,
        )
        for wl in wavelengths
    ]

    # ------------------------------------------------------------------
    # coordinates.csv – prefer the one inside the timepoint dir
    # ------------------------------------------------------------------
    csv_path: Path | None = None
    if tp_dir is not None and (tp_dir / "coordinates.csv").exists():
        csv_path = tp_dir / "coordinates.csv"
    elif (path / "coordinates.csv").exists():
        csv_path = path / "coordinates.csv"

    region_fovs: dict[str, list[FOVPosition]] = {}
    region_centers: dict[str, list[tuple[float, float, float]]] = {}
    nx: int = int(hw_params.get("Nx", 1))
    ny: int = int(hw_params.get("Ny", 1))

    if csv_path is not None:
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            reader.fieldnames = (
                [h.strip() for h in reader.fieldnames]
                if reader.fieldnames
                else reader.fieldnames
            )
            for row in reader:
                region_id = str(row["region"]).strip()

                # The root-level coordinates.csv has no fov column
                if "fov" in row:
                    fov_idx = int(row["fov"])
                    z_level = int(row.get("z_level", row.get("z", 0)))
                    if z_level != 0:
                        continue
                else:
                    # Root-level CSV: one row per region center, assign fov
                    # indices sequentially
                    fov_idx = len(region_fovs.get(region_id, []))

                x_mm = float(row["x (mm)"])
                y_mm = float(row["y (mm)"])
                has_z = "z (um)" in row and row["z (um)"].strip()
                z_um_val = float(row["z (um)"]) if has_z else 0.0

                fov_pos = FOVPosition(
                    fov_index=fov_idx,
                    x_mm=x_mm,
                    y_mm=y_mm,
                    z_um=z_um_val,
                )
                region_fovs.setdefault(region_id, []).append(fov_pos)
                region_centers.setdefault(region_id, []).append(
                    (x_mm, y_mm, z_um_val / 1000.0)
                )

        # Infer grid shape from unique x/y positions
        for _rid, fovs in region_fovs.items():
            unique_x = len({round(f.x_mm, 6) for f in fovs})
            unique_y = len({round(f.y_mm, 6) for f in fovs})
            if unique_x > 1:
                nx = unique_x
            if unique_y > 1:
                ny = unique_y

    # ------------------------------------------------------------------
    # Build Region objects
    # ------------------------------------------------------------------
    all_region_ids = sorted(region_fovs.keys()) if region_fovs else ["unknown"]

    regions: dict[str, Region] = {}
    for rid in all_region_ids:
        fovs = region_fovs.get(rid, [])
        positions = region_centers.get(rid, [(0.0, 0.0, 0.0)])
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        zs = [p[2] for p in positions]
        center: tuple[float, float, float] = (
            (min(xs) + max(xs)) / 2.0,
            (min(ys) + max(ys)) / 2.0,
            (min(zs) + max(zs)) / 2.0,
        )
        grid_params = GridParams(
            scan_size_mm=0.0,
            overlap_percent=0.0,
            nx=nx,
            ny=ny,
        )
        regions[rid] = Region(
            region_id=rid,
            center_mm=center,
            shape="Manual",
            fovs=fovs,
            grid_params=grid_params,
        )

    # ------------------------------------------------------------------
    # Z-stack / time-series from parameters
    # ------------------------------------------------------------------
    nz = int(hw_params.get("Nz", 1))
    z_stack: ZStackConfig | None = None
    if nz > 1:
        z_stack = ZStackConfig(
            nz=nz,
            delta_z_mm=float(hw_params.get("dz(um)", 1.5)) / 1000.0,
            direction="FROM_BOTTOM",
            use_piezo=False,
        )

    nt = int(hw_params.get("Nt", 1))
    time_series: TimeSeriesConfig | None = None
    if nt > 1:
        time_series = TimeSeriesConfig(
            nt=nt,
            delta_t_s=float(hw_params.get("dt(s)", 0.0)),
        )

    # ------------------------------------------------------------------
    # Scan config (minimal – no yaml scan section)
    # ------------------------------------------------------------------
    scan = ScanConfig(
        acquisition_pattern="S-Pattern",
        fov_pattern="S-Pattern",
        overlap_percent=None,
    )

    fmt = detect_format(path)

    return Acquisition(
        path=path,
        format=fmt,
        mode=AcquisitionMode.MANUAL,
        objective=objective,
        optical=optical,
        channels=channels,
        scan=scan,
        z_stack=z_stack,
        time_series=time_series,
        regions=regions,
    )


def open_acquisition(path: Path) -> Acquisition:
    """Parse a Squid acquisition directory and return a complete :class:`Acquisition`.

    Reads the following files:

    * ``acquisition.yaml``          – master metadata (mode, objective, channels,
                                      scan config, z-stack, time-series)
    * ``acquisition parameters.json`` – hardware params (tube_lens_mm)
    * ``coordinates.csv``           – FOV positions per region

    When ``acquisition.yaml`` is absent but ``acquisition parameters.json``
    exists, falls back to parsing the real Squid acquisition format directly.

    Parameters
    ----------
    path:
        Root directory of the Squid acquisition.

    Returns
    -------
    Acquisition
        Fully populated data model.
    """
    path = Path(path)

    # ------------------------------------------------------------------
    # If no acquisition.yaml, fall back to params-json-only path
    # ------------------------------------------------------------------
    yaml_path = path / "acquisition.yaml"
    if not yaml_path.exists():
        return _open_acquisition_from_params_json(path)

    # ------------------------------------------------------------------
    # 1. acquisition.yaml
    # ------------------------------------------------------------------
    with open(yaml_path) as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    acq_section: dict[str, Any] = raw.get("acquisition", {})
    widget_type: str = acq_section.get("widget_type", "wellplate")

    mode: AcquisitionMode
    if widget_type == "wellplate":
        mode = AcquisitionMode.WELLPLATE
    elif widget_type == "flexible":
        mode = AcquisitionMode.FLEXIBLE
    else:
        mode = AcquisitionMode.MANUAL

    # ------------------------------------------------------------------
    # 2. acquisition parameters.json  (hardware overrides)
    # ------------------------------------------------------------------
    params_path = path / "acquisition parameters.json"
    hw_params: dict[str, Any] = {}
    if params_path.exists():
        with open(params_path) as f:
            hw_params = json.load(f)

    tube_lens_mm: float = float(hw_params.get("tube_lens_mm", 180.0))

    # ------------------------------------------------------------------
    # 3. Objective
    # ------------------------------------------------------------------
    obj_raw: dict[str, Any] = raw.get("objective", {})
    objective = ObjectiveMetadata(
        name=str(obj_raw.get("name", "")),
        magnification=float(obj_raw.get("magnification", 1.0)),
        numerical_aperture=float(obj_raw.get("numerical_aperture", 0.0)),
        tube_lens_f_mm=float(obj_raw.get("tube_lens_f_mm", 180.0)),
        sensor_pixel_size_um=float(obj_raw.get("sensor_pixel_size_um", 1.85)),
        camera_binning=int(obj_raw.get("camera_binning", 1)),
        tube_lens_mm=tube_lens_mm,
    )

    # ------------------------------------------------------------------
    # 4. Optical metadata
    # ------------------------------------------------------------------
    immersion: str = str(obj_raw.get("immersion_medium", "air")).lower()
    if immersion not in IMMERSION_RI:
        immersion = "air"
    optical = OpticalMetadata(
        modality="widefield",
        immersion_medium=immersion,
        immersion_ri=IMMERSION_RI[immersion],
        numerical_aperture=objective.numerical_aperture,
        pixel_size_um=objective.pixel_size_um,
    )

    # ------------------------------------------------------------------
    # 5. Channels
    # ------------------------------------------------------------------
    channels_raw: list[dict[str, Any]] = raw.get("channels", [])
    channels: list[AcquisitionChannel] = [
        AcquisitionChannel(
            name=str(ch.get("name", f"Channel{i}")),
            illumination_source=str(ch.get("illumination_source", "LED")),
            illumination_intensity=float(ch.get("illumination_intensity", 0.0)),
            exposure_time_ms=float(ch.get("exposure_time_ms", 0.0)),
            emission_wavelength_nm=(
                float(ch["emission_wavelength_nm"])
                if ch.get("emission_wavelength_nm") is not None
                else None
            ),
            z_offset_um=float(ch.get("z_offset_um", 0.0)),
        )
        for i, ch in enumerate(channels_raw)
    ]

    # ------------------------------------------------------------------
    # 6. Scan config
    # ------------------------------------------------------------------
    scan_key = "wellplate_scan" if widget_type == "wellplate" else "flexible_scan"
    scan_raw: dict[str, Any] = raw.get(scan_key, raw.get("scan", {}))
    scan = ScanConfig(
        acquisition_pattern=str(scan_raw.get("acquisition_pattern", "S-Pattern")),
        fov_pattern=str(scan_raw.get("fov_pattern", "S-Pattern")),
        overlap_percent=(
            float(scan_raw["overlap_percent"])
            if scan_raw.get("overlap_percent") is not None
            else None
        ),
    )

    # Region IDs declared in the yaml scan section
    region_ids_yaml: list[str] = list(scan_raw.get("regions", []))
    nx: int = int(scan_raw.get("nx", 1))
    ny: int = int(scan_raw.get("ny", 1))

    # ------------------------------------------------------------------
    # 7. Z-stack / time-series
    # ------------------------------------------------------------------
    z_stack: ZStackConfig | None = None
    z_raw: dict[str, Any] | None = raw.get("z_stack")
    if z_raw:
        z_stack = ZStackConfig(
            nz=int(z_raw["nz"]),
            delta_z_mm=float(z_raw["delta_z_mm"]),
            direction=str(z_raw.get("direction", "FROM_BOTTOM")),
            use_piezo=bool(z_raw.get("use_piezo", False)),
        )

    time_series: TimeSeriesConfig | None = None
    ts_raw: dict[str, Any] | None = raw.get("time_series")
    if ts_raw:
        time_series = TimeSeriesConfig(
            nt=int(ts_raw["nt"]),
            delta_t_s=float(ts_raw["delta_t_s"]),
        )

    # ------------------------------------------------------------------
    # 8. coordinates.csv  → group FOV positions by region
    # ------------------------------------------------------------------
    csv_path = path / "coordinates.csv"
    region_fovs: dict[str, list[FOVPosition]] = {}
    region_centers: dict[str, list[tuple[float, float, float]]] = {}

    if csv_path.exists():
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            # Strip BOM / whitespace from headers
            reader.fieldnames = (
                [h.strip() for h in reader.fieldnames]
                if reader.fieldnames
                else reader.fieldnames
            )
            for row in reader:
                region_id = str(row["region"]).strip()
                fov_idx = int(row["fov"])
                z_level = int(row.get("z_level", row.get("z", 0)))
                x_mm = float(row["x (mm)"])
                y_mm = float(row["y (mm)"])
                z_um_val = float(row["z (um)"]) if "z (um)" in row else 0.0

                # Only keep fov row for z_level == 0 to avoid duplicates
                if z_level != 0:
                    continue

                fov_pos = FOVPosition(
                    fov_index=fov_idx,
                    x_mm=x_mm,
                    y_mm=y_mm,
                    z_um=z_um_val,
                )
                region_fovs.setdefault(region_id, []).append(fov_pos)
                region_centers.setdefault(region_id, []).append((x_mm, y_mm, z_um_val / 1000.0))

    # ------------------------------------------------------------------
    # 9. Build Region objects
    # ------------------------------------------------------------------
    # Fall back to region IDs from csv if yaml list is empty
    all_region_ids = region_ids_yaml or sorted(region_fovs.keys())

    overlap = scan.overlap_percent or 0.0

    regions: dict[str, Region] = {}
    for rid in all_region_ids:
        fovs = region_fovs.get(rid, [])
        positions = region_centers.get(rid, [(0.0, 0.0, 0.0)])
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        zs = [p[2] for p in positions]
        center: tuple[float, float, float] = (
            (min(xs) + max(xs)) / 2.0,
            (min(ys) + max(ys)) / 2.0,
            (min(zs) + max(zs)) / 2.0,
        )
        grid_params = GridParams(
            scan_size_mm=0.0,  # not directly stored
            overlap_percent=overlap,
            nx=nx,
            ny=ny,
        )
        regions[rid] = Region(
            region_id=rid,
            center_mm=center,
            shape="Square",
            fovs=fovs,
            grid_params=grid_params,
        )

    # ------------------------------------------------------------------
    # 10. Detect format
    # ------------------------------------------------------------------
    fmt = detect_format(path)

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
