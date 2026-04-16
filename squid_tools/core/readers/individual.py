"""Reader for Squid INDIVIDUAL_IMAGES format."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

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
    def __init__(self) -> None:
        self._path: Path | None = None
        self._channel_names: list[str] = []

    @classmethod
    def detect(cls, path: Path) -> bool:
        if (path / "ome_tiff").exists():
            return False
        if (path / "plate.ome.zarr").exists():
            return False
        tp0 = path / "0"
        if not tp0.is_dir():
            return False
        if not list(tp0.glob("*.tiff")):
            return False
        # Need at least coordinates.csv or acquisition.yaml
        has_coords = (tp0 / "coordinates.csv").exists() or (path / "coordinates.csv").exists()
        has_yaml = (path / "acquisition.yaml").exists()
        has_json = (path / "acquisition parameters.json").exists()
        return has_coords and (has_yaml or has_json)

    def read_metadata(self, path: Path) -> Acquisition:
        self._path = path

        # Load acquisition.yaml if available
        meta: dict[str, Any] = {}
        if (path / "acquisition.yaml").exists():
            with open(path / "acquisition.yaml") as f:
                meta = yaml.safe_load(f) or {}

        # Load acquisition parameters.json (always try)
        params: dict[str, Any] = {}
        params_file = path / "acquisition parameters.json"
        if params_file.exists():
            with open(params_file) as f:
                params = json.load(f)

        # Objective: prefer yaml, fall back to json
        obj_meta = meta.get("objective", {})
        obj_json = params.get("objective", {})
        magnification = obj_meta.get("magnification") or obj_json.get("magnification", 1.0)
        sensor_px = params.get("sensor_pixel_size_um", 7.52)
        tube_lens_mm = params.get("tube_lens_mm", 180.0)
        tube_lens_f = obj_json.get("tube_lens_f_mm", tube_lens_mm)
        pixel_size = obj_meta.get("pixel_size_um") or (sensor_px / magnification)

        objective = ObjectiveMetadata(
            name=obj_meta.get("name") or obj_json.get("name", "unknown"),
            magnification=magnification,
            pixel_size_um=pixel_size,
            numerical_aperture=obj_json.get("NA"),
            sensor_pixel_size_um=sensor_px,
            tube_lens_mm=tube_lens_mm,
            tube_lens_f_mm=tube_lens_f,
        )

        # Channels: prefer yaml, fall back to auto-detect from filenames
        channels: list[AcquisitionChannel] = []
        if meta.get("channels"):
            for ch in meta["channels"]:
                illum = ch.get("illumination_settings", {})
                cam = ch.get("camera_settings", {})
                channels.append(AcquisitionChannel(
                    name=ch.get("name", ""),
                    illumination_source=illum.get("illumination_channel", ""),
                    illumination_intensity=illum.get("intensity", 0.0),
                    exposure_time_ms=cam.get("exposure_time_ms", 0.0),
                    z_offset_um=ch.get("z_offset_um", 0.0),
                ))
        else:
            # Auto-detect channels from filenames in timepoint 0
            channels = self._detect_channels_from_files(path / "0")
        self._channel_names = [ch.name for ch in channels]

        # Mode
        acq_meta = meta.get("acquisition", {})
        widget_type = acq_meta.get("widget_type", "")
        if widget_type in ("wellplate", "flexible"):
            mode = AcquisitionMode(widget_type)
        else:
            mode = AcquisitionMode.MANUAL

        # Scan config
        scan = ScanConfig()
        if "wellplate_scan" in meta:
            scan = ScanConfig(overlap_percent=meta["wellplate_scan"].get("overlap_percent"))
        elif "flexible_scan" in meta:
            scan = ScanConfig(overlap_percent=meta["flexible_scan"].get("overlap_percent"))

        # Z-stack: prefer yaml, fall back to json
        z_stack = None
        zs_meta = meta.get("z_stack", {})
        nz = zs_meta.get("nz") or params.get("Nz", 1)
        if nz > 0:
            dz = zs_meta.get("delta_z_mm") or (params.get("dz(um)", 1.5) / 1000)
            direction = (
                "FROM_BOTTOM"
                if zs_meta.get("config", "FROM_BOTTOM") == "FROM_BOTTOM"
                else "FROM_TOP"
            )
            z_stack = ZStackConfig(
                nz=nz, delta_z_mm=dz,
                direction=direction,
                use_piezo=zs_meta.get("use_piezo", False),
            )

        # Time series
        time_series = None
        ts_meta = meta.get("time_series", {})
        nt = ts_meta.get("nt") or params.get("Nt", 1)
        if nt > 0:
            dt = ts_meta.get("delta_t_s") or params.get("dt(s)", 0.0)
            time_series = TimeSeriesConfig(nt=nt, delta_t_s=dt)

        # Regions from coordinates.csv
        regions = self._parse_regions(path, meta)

        return Acquisition(
            path=path, format=AcquisitionFormat.INDIVIDUAL_IMAGES, mode=mode,
            objective=objective, channels=channels, scan=scan,
            z_stack=z_stack, time_series=time_series, regions=regions,
        )

    def _detect_channels_from_files(self, tp_dir: Path) -> list[AcquisitionChannel]:
        """Auto-detect channel names from TIFF filenames in a timepoint directory.

        Filename pattern: {region}_{fov}_{z}_{channel_name}.tiff
        We look at fov 0, z 0 to find all channel names.
        """
        channels: list[AcquisitionChannel] = []
        seen: set[str] = set()
        for f in sorted(tp_dir.glob("*.tiff")):
            parts = f.stem.split("_", 3)
            if len(parts) >= 4:
                ch_name = parts[3]
                if ch_name not in seen:
                    seen.add(ch_name)
                    channels.append(AcquisitionChannel(name=ch_name))
        return channels

    def _parse_regions(self, path: Path, meta: dict[str, Any]) -> dict[str, Region]:
        regions: dict[str, Region] = {}
        # Try timepoint dir first, then root
        coords_file = path / "0" / "coordinates.csv"
        if not coords_file.exists():
            coords_file = path / "coordinates.csv"
        if not coords_file.exists():
            return regions

        # Pre-build center lookup from scan metadata for all regions
        center_lookup: dict[str, tuple[float, float, float]] = {}
        for scan_key in ("wellplate_scan", "flexible_scan"):
            scan_meta = meta.get(scan_key, {})
            for r in scan_meta.get("regions", scan_meta.get("positions", [])):
                name = str(r.get("name"))
                c = r.get("center_mm", [0, 0, 0])
                center_lookup[name] = (float(c[0]), float(c[1]), float(c[2]))

        with open(coords_file) as f:
            reader = csv.reader(f)
            header = next(reader)
            # Resolve column indices once from the header
            col = {name.strip(): i for i, name in enumerate(header)}
            rid_idx = col["region"]
            fov_idx = col["fov"]
            x_idx = col["x (mm)"]
            y_idx = col["y (mm)"]
            z_idx = col.get("z (um)")

            seen_fovs: dict[str, set[int]] = {}
            for row in reader:
                rid = row[rid_idx]
                fov_index = int(row[fov_idx])
                if rid not in regions:
                    center = center_lookup.get(rid, (0.0, 0.0, 0.0))
                    regions[rid] = Region(region_id=rid, center_mm=center)
                    seen_fovs[rid] = set()
                if fov_index not in seen_fovs[rid]:
                    seen_fovs[rid].add(fov_index)
                    regions[rid].fovs.append(FOVPosition(
                        fov_index=fov_index,
                        x_mm=float(row[x_idx]),
                        y_mm=float(row[y_idx]),
                        z_um=float(row[z_idx]) if z_idx is not None else None,
                    ))
        return regions

    def read_frame(self, key: FrameKey) -> np.ndarray:
        if self._path is None:
            raise RuntimeError("Must call read_metadata before read_frame")
        channel_name = self._channel_names[key.channel]
        fname = f"{key.region}_{key.fov}_{key.z}_{channel_name}.tiff"
        frame_path = self._path / str(key.timepoint) / fname
        return tifffile.imread(str(frame_path))
