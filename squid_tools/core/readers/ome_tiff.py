"""Reader for Squid OME-TIFF format."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, cast

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
    def __init__(self) -> None:
        self._path: Path | None = None
        self._fov_files: dict[tuple[str, int], Path] = {}

    @classmethod
    def detect(cls, path: Path) -> bool:
        if not (path / "acquisition.yaml").exists():
            return False
        ome_dir = path / "ome_tiff"
        return ome_dir.is_dir() and bool(list(ome_dir.glob("*.ome.tiff")))

    def read_metadata(self, path: Path) -> Acquisition:
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
        if widget_type in ("wellplate", "flexible"):
            mode = AcquisitionMode(widget_type)
        else:
            mode = AcquisitionMode.MANUAL

        scan = ScanConfig()
        if "wellplate_scan" in meta:
            scan = ScanConfig(overlap_percent=meta["wellplate_scan"].get("overlap_percent"))
        elif "flexible_scan" in meta:
            scan = ScanConfig(overlap_percent=meta["flexible_scan"].get("overlap_percent"))

        z_stack = None
        zs_meta = meta.get("z_stack", {})
        if zs_meta.get("nz", 0) > 0:
            z_stack = ZStackConfig(
                nz=zs_meta["nz"], delta_z_mm=zs_meta.get("delta_z_mm", 0.001),
                direction="FROM_BOTTOM" if zs_meta.get("config") == "FROM_BOTTOM" else "FROM_TOP",
                use_piezo=zs_meta.get("use_piezo", False),
            )

        time_series = None
        ts_meta = meta.get("time_series", {})
        if ts_meta.get("nt", 0) > 0:
            time_series = TimeSeriesConfig(
                nt=ts_meta["nt"], delta_t_s=ts_meta.get("delta_t_s", 1.0)
            )

        regions = self._parse_regions_from_files(path, meta)

        return Acquisition(
            path=path, format=AcquisitionFormat.OME_TIFF, mode=mode,
            objective=objective, channels=channels, scan=scan,
            z_stack=z_stack, time_series=time_series, regions=regions,
        )

    def _parse_regions_from_files(self, path: Path, meta: dict[str, Any]) -> dict[str, Region]:
        regions: dict[str, Region] = {}
        ome_dir = path / "ome_tiff"

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

        coords_file = path / "0" / "coordinates.csv"
        if coords_file.exists():
            with open(coords_file) as coords_fh:
                reader = csv.DictReader(coords_fh)
                for row in reader:
                    rid = str(row["region"])
                    fov_idx = int(row["fov"])
                    if rid in regions:
                        existing = {fv.fov_index for fv in regions[rid].fovs}
                        if fov_idx not in existing:
                            regions[rid].fovs.append(FOVPosition(
                                fov_index=fov_idx, x_mm=float(row["x (mm)"]),
                                y_mm=float(row["y (mm)"]), z_um=float(row.get("z (um)", 0)),
                            ))
        return regions

    def read_frame(self, key: FrameKey) -> np.ndarray:
        file_key = (key.region, key.fov)
        if file_key not in self._fov_files:
            raise FileNotFoundError(f"No OME-TIFF for region={key.region}, fov={key.fov}")
        fpath = self._fov_files[file_key]
        with tifffile.TiffFile(str(fpath)) as tif:
            data = cast(np.ndarray, tif.asarray())
            # tifffile may squeeze singleton T dimension; use actual ndim to index
            # Full TZCYX = 5 dims; squeezed ZCYX = 4 dims
            if data.ndim == 5:
                return data[key.timepoint, key.z, key.channel]  # type: ignore[no-any-return]
            elif data.ndim == 4:
                # T was squeezed (nt=1); axes are ZCYX
                return data[key.z, key.channel]  # type: ignore[no-any-return]
            else:
                raise ValueError(f"Unexpected OME-TIFF array ndim={data.ndim} in {fpath}")
