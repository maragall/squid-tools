"""Synthetic Squid acquisition fixture generator.

Creates realistic Squid acquisition directories for testing.
Supports both INDIVIDUAL_IMAGES and OME_TIFF formats.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import tifffile
import yaml

# ---------------------------------------------------------------------------
# acquisition.yaml
# ---------------------------------------------------------------------------

def generate_acquisition_yaml(
    path: Path,
    widget_type: str = "wellplate",
    n_regions: int = 1,
    region_ids: Sequence[str] | None = None,
    nx: int = 3,
    ny: int = 3,
    nz: int = 1,
    nt: int = 1,
    n_channels: int = 2,
    overlap_percent: float = 10.0,
    pixel_size_um: float = 0.645,
    sensor_pixel_size_um: float = 1.85,
    magnification: float = 20.0,
) -> Path:
    """Write acquisition.yaml to *path* (directory).

    Returns the path to the written file.
    """
    if region_ids is None:
        region_ids = [f"R{i}" for i in range(n_regions)]

    channels = []
    for ch in range(n_channels):
        channels.append({
            "name": f"Channel{ch}",
            "illumination_source": "LED",
            "illumination_intensity": 50.0,
            "exposure_time_ms": 100.0,
            "emission_wavelength_nm": 488.0 + ch * 50,
            "z_offset_um": 0.0,
        })

    objective = {
        "name": f"{int(magnification)}x",
        "magnification": magnification,
        "numerical_aperture": 0.4,
        "tube_lens_f_mm": 180.0,
        "sensor_pixel_size_um": sensor_pixel_size_um,
        "camera_binning": 1,
        "tube_lens_mm": 180.0,
    }

    z_stack = None
    if nz > 1:
        z_stack = {
            "nz": nz,
            "delta_z_mm": 0.001,
            "direction": "FROM_BOTTOM",
            "use_piezo": False,
        }

    time_series = None
    if nt > 1:
        time_series = {
            "nt": nt,
            "delta_t_s": 60.0,
        }

    scan_section_key = "wellplate_scan" if widget_type == "wellplate" else "flexible_scan"
    scan_section = {
        "acquisition_pattern": "S-Pattern",
        "fov_pattern": "S-Pattern",
        "overlap_percent": overlap_percent,
        "regions": list(region_ids),
        "nx": nx,
        "ny": ny,
    }

    data = {
        "acquisition": {
            "widget_type": widget_type,
            "format": "INDIVIDUAL_IMAGES",  # overridden by caller if needed
        },
        "objective": objective,
        "channels": channels,
        scan_section_key: scan_section,
    }
    if z_stack is not None:
        data["z_stack"] = z_stack
    if time_series is not None:
        data["time_series"] = time_series

    out = path / "acquisition.yaml"
    with open(out, "w") as f:
        yaml.dump(data, f, default_flow_style=False)
    return out


# ---------------------------------------------------------------------------
# coordinates.csv
# ---------------------------------------------------------------------------

def generate_coordinates_csv(
    path: Path,
    region_ids: Sequence[str] | None = None,
    nx: int = 3,
    ny: int = 3,
    nz: int = 1,
    pixel_size_um: float = 0.645,
    overlap_percent: float = 10.0,
    img_width: int = 256,
) -> Path:
    """Write coordinates.csv to *path* (directory).

    Grid positions are computed from pixel_size_um, img_width, and
    overlap_percent, matching Squid's real output format.
    Returns the path to the written file.
    """
    if region_ids is None:
        region_ids = ["R0"]

    # Step size in mm
    step_mm = img_width * pixel_size_um * (1.0 - overlap_percent / 100.0) / 1000.0

    rows = ["region,fov,z_level,x (mm),y (mm),z (um),time"]
    for region in region_ids:
        fov = 0
        for iy in range(ny):
            # S-pattern: reverse every other row
            xs = range(nx) if iy % 2 == 0 else range(nx - 1, -1, -1)
            for ix in xs:
                x_mm = ix * step_mm
                y_mm = iy * step_mm
                for z_level in range(nz):
                    z_um = z_level * 1.0  # 1 µm steps
                    rows.append(
                        f"{region},{fov},{z_level},{x_mm:.6f},{y_mm:.6f},{z_um:.3f},0"
                    )
                fov += 1

    out = path / "coordinates.csv"
    out.write_text("\n".join(rows) + "\n")
    return out


# ---------------------------------------------------------------------------
# acquisition parameters.json
# ---------------------------------------------------------------------------

def generate_acquisition_params_json(
    path: Path,
    sensor_pixel_size_um: float = 1.85,
    tube_lens_mm: float = 180.0,
) -> Path:
    """Write 'acquisition parameters.json' to *path* (directory).

    Returns the path to the written file.
    """
    data = {
        "sensor_pixel_size_um": sensor_pixel_size_um,
        "tube_lens_mm": tube_lens_mm,
    }
    out = path / "acquisition parameters.json"
    with open(out, "w") as f:
        json.dump(data, f, indent=2)
    return out


# ---------------------------------------------------------------------------
# Individual TIFF images
# ---------------------------------------------------------------------------

def generate_individual_images(
    path: Path,
    region_ids: Sequence[str] | None = None,
    nx: int = 3,
    ny: int = 3,
    nz: int = 1,
    nt: int = 1,
    n_channels: int = 2,
    img_shape: tuple[int, int] = (256, 256),
) -> None:
    """Create individual TIFF files under *path*.

    File naming: ``{path}/{timepoint:05d}/{region}_{fov:05d}_C{ch:02d}.tiff``
    Each TIFF has a JSON metadata dict in the ImageDescription tag.
    """
    if region_ids is None:
        region_ids = ["R0"]

    rng = np.random.default_rng(seed=42)
    n_fovs = nx * ny

    for t in range(nt):
        t_dir = path / f"{t:05d}"
        t_dir.mkdir(parents=True, exist_ok=True)
        for region in region_ids:
            for fov in range(n_fovs):
                for ch in range(n_channels):
                    img = rng.integers(0, 65535, size=img_shape, dtype=np.uint16)
                    metadata = {
                        "region": region,
                        "fov": fov,
                        "channel": ch,
                        "timepoint": t,
                        "z_level": 0,
                    }
                    fname = t_dir / f"{region}_{fov:05d}_C{ch:02d}.tiff"
                    tifffile.imwrite(
                        fname,
                        img,
                        description=json.dumps(metadata),
                    )

    # For multi-z, write z-slices as separate files per z_level
    # (Squid stores each z as a separate frame; simplify: one file per z)
    if nz > 1:
        for t in range(nt):
            t_dir = path / f"{t:05d}"
            for region in region_ids:
                for fov in range(n_fovs):
                    for ch in range(n_channels):
                        # Remove the z=0 file and recreate with z in name
                        plain = t_dir / f"{region}_{fov:05d}_C{ch:02d}.tiff"
                        if plain.exists():
                            plain.unlink()
                        for z in range(nz):
                            img = rng.integers(0, 65535, size=img_shape, dtype=np.uint16)
                            metadata = {
                                "region": region,
                                "fov": fov,
                                "channel": ch,
                                "timepoint": t,
                                "z_level": z,
                            }
                            fname = t_dir / f"{region}_{fov:05d}_z{z:03d}_C{ch:02d}.tiff"
                            tifffile.imwrite(
                                fname,
                                img,
                                description=json.dumps(metadata),
                            )


# ---------------------------------------------------------------------------
# OME-TIFF images
# ---------------------------------------------------------------------------

def generate_ome_tiff(
    path: Path,
    region_ids: Sequence[str] | None = None,
    nx: int = 3,
    ny: int = 3,
    nz: int = 1,
    nt: int = 1,
    n_channels: int = 2,
    img_shape: tuple[int, int] = (256, 256),
) -> None:
    """Create OME-TIFF files under *path*/ome_tiff/.

    File naming: ``{path}/ome_tiff/{region}_{fov:05d}.ome.tiff``
    Axis order: TZCYX.
    """
    if region_ids is None:
        region_ids = ["R0"]

    out_dir = path / "ome_tiff"
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(seed=42)
    n_fovs = nx * ny

    for region in region_ids:
        for fov in range(n_fovs):
            # Shape: T, Z, C, Y, X
            vol = rng.integers(0, 65535, size=(nt, nz, n_channels, *img_shape), dtype=np.uint16)
            fname = out_dir / f"{region}_{fov:05d}.ome.tiff"
            tifffile.imwrite(
                fname,
                vol,
                imagej=False,
                photometric="minisblack",
                metadata={"axes": "TZCYX"},
            )


# ---------------------------------------------------------------------------
# Top-level factory
# ---------------------------------------------------------------------------

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

    Parameters
    ----------
    base_path:
        Root directory to write into.
    fmt:
        ``"INDIVIDUAL_IMAGES"`` or ``"OME_TIFF"``.
    widget_type:
        ``"wellplate"`` or ``"flexible"``.
    n_regions:
        Number of scan regions.
    nx, ny:
        Grid dimensions (FOVs per row / column).
    nz:
        Number of z-slices.
    nt:
        Number of timepoints.
    n_channels:
        Number of fluorescence channels.
    img_shape:
        (height, width) of each 2-D frame in pixels.

    Returns
    -------
    Path
        The acquisition root directory (``base_path``).
    """
    base_path = Path(base_path)
    base_path.mkdir(parents=True, exist_ok=True)

    region_ids = [f"R{i}" for i in range(n_regions)]

    pixel_size_um = 0.645
    sensor_pixel_size_um = 1.85
    magnification = 20.0
    overlap_percent = 10.0
    img_width = img_shape[1]

    generate_acquisition_yaml(
        base_path,
        widget_type=widget_type,
        n_regions=n_regions,
        region_ids=region_ids,
        nx=nx,
        ny=ny,
        nz=nz,
        nt=nt,
        n_channels=n_channels,
        overlap_percent=overlap_percent,
        pixel_size_um=pixel_size_um,
        sensor_pixel_size_um=sensor_pixel_size_um,
        magnification=magnification,
    )

    generate_coordinates_csv(
        base_path,
        region_ids=region_ids,
        nx=nx,
        ny=ny,
        nz=nz,
        pixel_size_um=pixel_size_um,
        overlap_percent=overlap_percent,
        img_width=img_width,
    )

    generate_acquisition_params_json(
        base_path,
        sensor_pixel_size_um=sensor_pixel_size_um,
        tube_lens_mm=180.0,
    )

    if fmt == "INDIVIDUAL_IMAGES":
        generate_individual_images(
            base_path,
            region_ids=region_ids,
            nx=nx,
            ny=ny,
            nz=nz,
            nt=nt,
            n_channels=n_channels,
            img_shape=img_shape,
        )
    elif fmt == "OME_TIFF":
        generate_ome_tiff(
            base_path,
            region_ids=region_ids,
            nx=nx,
            ny=ny,
            nz=nz,
            nt=nt,
            n_channels=n_channels,
            img_shape=img_shape,
        )
    else:
        raise ValueError(f"Unsupported format: {fmt!r}. Use 'INDIVIDUAL_IMAGES' or 'OME_TIFF'.")

    return base_path
