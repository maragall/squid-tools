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
import zarr


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
    path.mkdir(parents=True, exist_ok=True)
    pixel_size_um = 0.325
    step_mm = pixel_size_um * image_shape[1] * (1 - overlap_percent / 100) / 1000
    channel_names = [f"channel_{i}" for i in range(nc)]

    fov_positions: list[dict[str, float]] = []
    center_x = nx * step_mm / 2
    center_y = ny * step_mm / 2
    for iy in range(ny):
        for ix in range(nx):
            fov_positions.append({"x_mm": ix * step_mm, "y_mm": iy * step_mm})

    acq_yaml = {
        "acquisition": {
            "experiment_id": "test_acquisition",
            "start_time": "2026-01-01T00:00:00",
            "widget_type": "wellplate" if wellplate else "flexible",
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

    with open(path / "acquisition parameters.json", "w") as f:
        json.dump({"sensor_pixel_size_um": 3.45, "tube_lens_mm": 50.0}, f)

    for t in range(nt):
        tp_dir = path / str(t)
        tp_dir.mkdir(exist_ok=True)
        rows: list[dict[str, object]] = []
        for fov_idx, pos in enumerate(fov_positions):
            for z in range(nz):
                for _c, ch_name in enumerate(channel_names):
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
    path.mkdir(parents=True, exist_ok=True)
    pixel_size_um = 0.325
    step_mm = pixel_size_um * image_shape[1] * 0.85 / 1000
    channel_names = [f"channel_{i}" for i in range(nc)]

    acq_yaml = {
        "acquisition": {
            "experiment_id": "test_ome",
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
            "regions": [{"name": region_id, "center_mm": [0.0, 0.0, 0.0], "shape": "Square"}],
        },
    }
    with open(path / "acquisition.yaml", "w") as f:
        yaml.dump(acq_yaml, f, default_flow_style=False)
    with open(path / "acquisition parameters.json", "w") as f:
        json.dump({"sensor_pixel_size_um": 3.45, "tube_lens_mm": 50.0}, f)

    ome_dir = path / "ome_tiff"
    ome_dir.mkdir()
    fov_idx = 0
    for _iy in range(ny):
        for _ix in range(nx):
            fname = f"{region_id}_{fov_idx:05}.ome.tiff"
            data = np.random.randint(0, 4095, (nt, nz, nc, *image_shape), dtype=np.uint16)
            metadata = {
                "axes": "TZCYX",
                "Channel": {"Name": channel_names},
                "PhysicalSizeX": pixel_size_um,
                "PhysicalSizeY": pixel_size_um,
            }
            tifffile.imwrite(str(ome_dir / fname), data, ome=True, metadata=metadata)
            fov_idx += 1

    tp_dir = path / "0"
    tp_dir.mkdir()
    rows_ome: list[dict[str, object]] = []
    fov_idx = 0
    for iy in range(ny):
        for ix in range(nx):
            for z in range(nz):
                rows_ome.append({
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
        writer = csv.DictWriter(f, fieldnames=list(rows_ome[0].keys()))
        writer.writeheader()
        writer.writerows(rows_ome)

    return path


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
    root = zarr.open_group(str(plate_path), mode="w")

    n_fovs = nx * ny
    for fov_idx in range(n_fovs):
        fov_group = root.require_group(f"{row}/{col}/{fov_idx}/0")
        data = np.random.randint(0, 4095, (nt, nc, nz, *image_shape), dtype=np.uint16)
        fov_group.create_array("data", data=data, chunks=(1, 1, 1, *image_shape))

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
