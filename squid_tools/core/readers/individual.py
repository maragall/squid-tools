"""Reader for Squid INDIVIDUAL_IMAGES format."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np
import tifffile

from squid_tools.core.data_model import (
    Acquisition,
    AcquisitionChannel,
    AcquisitionFormat,
    FOVPosition,
    FrameKey,
    Region,
)
from squid_tools.core.readers._squid_metadata import (
    build_mode,
    build_objective,
    build_scan,
    build_time_series,
    build_z_stack,
    channel_from_yaml,
    load_yaml_and_json,
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
        yaml_meta, json_params = load_yaml_and_json(path)

        objective = build_objective(yaml_meta, json_params)

        channels: list[AcquisitionChannel] = []
        if yaml_meta.get("channels"):
            channels = [channel_from_yaml(ch) for ch in yaml_meta["channels"]]
        else:
            channels = self._detect_channels_from_files(path / "0")
        self._channel_names = [ch.name for ch in channels]

        mode = build_mode(yaml_meta)
        scan = build_scan(yaml_meta)
        z_stack = build_z_stack(yaml_meta, json_params)
        time_series = build_time_series(yaml_meta, json_params)
        regions = self._parse_regions(path, yaml_meta)

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
        if not 0 <= key.channel < len(self._channel_names):
            raise ValueError(
                f"Channel index {key.channel} out of range "
                f"[0, {len(self._channel_names)}); "
                f"acquisition has {len(self._channel_names)} channel(s): "
                f"{self._channel_names}",
            )
        channel_name = self._channel_names[key.channel]
        fname = f"{key.region}_{key.fov}_{key.z}_{channel_name}.tiff"
        frame_path = self._path / str(key.timepoint) / fname
        if not frame_path.exists():
            raise FileNotFoundError(
                f"Frame file not found at {frame_path}. "
                f"FrameKey={key}. The acquisition's metadata expected this "
                f"file but it is missing — likely a partial export or a "
                f"channel-name mismatch between configurations.xml and "
                f"the on-disk filenames.",
            )
        return tifffile.imread(str(frame_path))
