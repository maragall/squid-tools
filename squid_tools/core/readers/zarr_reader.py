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
from typing import Any, cast

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
            channels.append(
                AcquisitionChannel(
                    name=ch.get("name", ""),
                    illumination_source=illum.get("illumination_channel", ""),
                    illumination_intensity=illum.get("intensity", 0.0),
                    exposure_time_ms=cam.get("exposure_time_ms", 0.0),
                    z_offset_um=ch.get("z_offset_um", 0.0),
                )
            )

        acq_meta = meta.get("acquisition", {})
        widget_type = acq_meta.get("widget_type", "wellplate")
        mode = (
            AcquisitionMode(widget_type)
            if widget_type in ("wellplate", "flexible")
            else AcquisitionMode.MANUAL
        )

        scan = ScanConfig()
        if "wellplate_scan" in meta:
            scan = ScanConfig(overlap_percent=meta["wellplate_scan"].get("overlap_percent"))

        z_stack = None
        zs_meta = meta.get("z_stack", {})
        if zs_meta.get("nz", 0) > 0:
            z_stack = ZStackConfig(
                nz=zs_meta["nz"],
                delta_z_mm=zs_meta.get("delta_z_mm", 0.001),
                direction=(
                    "FROM_BOTTOM" if zs_meta.get("config") == "FROM_BOTTOM" else "FROM_TOP"
                ),
                use_piezo=zs_meta.get("use_piezo", False),
            )

        time_series = None
        ts_meta = meta.get("time_series", {})
        if ts_meta.get("nt", 0) > 0:
            time_series = TimeSeriesConfig(
                nt=ts_meta["nt"], delta_t_s=ts_meta.get("delta_t_s", 1.0)
            )

        # Open Zarr store and discover FOVs
        plate_path = path / "plate.ome.zarr"
        self._root = zarr.open_group(str(plate_path), mode="r")

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

    def _parse_regions(self, path: Path, meta: dict[str, Any]) -> dict[str, Region]:
        """Build regions from coordinates.csv and Zarr store structure."""
        regions: dict[str, Region] = {}

        # Discover FOV groups in the Zarr store
        if self._root is not None:
            for row_name in sorted(self._root.group_keys()):
                row_group = cast(zarr.Group, self._root[row_name])
                for col_name in sorted(row_group.group_keys()):
                    col_group = cast(zarr.Group, row_group[col_name])
                    for fov_name in sorted(col_group.group_keys()):
                        fov_group = cast(zarr.Group, col_group[fov_name])
                        if "0" in fov_group:
                            fov_idx = int(fov_name)
                            self._fov_groups[("0", fov_idx)] = cast(zarr.Group, fov_group["0"])

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
                        regions[rid].fovs.append(
                            FOVPosition(
                                fov_index=fov_idx,
                                x_mm=float(row["x (mm)"]),
                                y_mm=float(row["y (mm)"]),
                                z_um=float(row.get("z (um)", 0)),
                            )
                        )

        return regions

    def read_frame(self, key: FrameKey) -> np.ndarray:
        """Load a single 2D frame from the Zarr store.

        Zarr HCS data shape: (T, C, Z, Y, X).
        """
        fov_key = (key.region, key.fov)
        if fov_key not in self._fov_groups:
            raise FileNotFoundError(f"No Zarr data for region={key.region}, fov={key.fov}")

        group = self._fov_groups[fov_key]
        data = cast("zarr.Array[Any]", group["data"])
        return np.array(data[key.timepoint, key.channel, key.z])
