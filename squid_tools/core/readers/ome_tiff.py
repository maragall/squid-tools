"""Reader for Squid OME-TIFF format."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, cast

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
    parse_channels_from_xml,
)
from squid_tools.core.readers.base import FormatReader


class OMETiffReader(FormatReader):
    def __init__(self) -> None:
        self._path: Path | None = None
        self._fov_files: dict[tuple[str, int], Path] = {}
        # Memory-mapped per-FOV arrays. Keyed by (region, fov). Holds file
        # handles open via mmap; OS pages in only the bytes we slice.
        self._mmap_cache: dict[tuple[str, int], np.ndarray] = {}

    @classmethod
    def detect(cls, path: Path) -> bool:
        ome_dir = path / "ome_tiff"
        if not (ome_dir.is_dir() and any(ome_dir.glob("*.ome.tiff"))):
            return False
        has_yaml = (path / "acquisition.yaml").exists()
        has_json = (path / "acquisition parameters.json").exists()
        return has_yaml or has_json

    def read_metadata(self, path: Path) -> Acquisition:
        self._path = path
        yaml_meta, json_params = load_yaml_and_json(path)

        objective = build_objective(yaml_meta, json_params)

        # Channels: YAML when present (canonical), else parse Squid's
        # configurations.xml for <mode Selected="true"> entries.
        channels: list[AcquisitionChannel] = []
        if yaml_meta.get("channels"):
            channels = [channel_from_yaml(ch) for ch in yaml_meta["channels"]]
        else:
            xml_path = path / "configurations.xml"
            if xml_path.exists():
                channels = parse_channels_from_xml(xml_path)

        mode = build_mode(yaml_meta)
        scan = build_scan(yaml_meta)
        z_stack = build_z_stack(yaml_meta, json_params)
        time_series = build_time_series(yaml_meta, json_params)
        regions = self._parse_regions_from_files(path, yaml_meta)

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
        # Memory-map the file once per FOV. The OS pages in only the bytes
        # we slice; without this the previous tif.asarray() pulled the whole
        # multi-hundred-MB z-stack into RAM on every single frame request,
        # making compute_contrast at startup do tens of GB of disk I/O on
        # OME-TIFF datasets and the GUI never paint.
        if file_key not in self._mmap_cache:
            self._mmap_cache[file_key] = cast(
                np.ndarray, tifffile.memmap(str(fpath), mode="r"),
            )
        arr = self._mmap_cache[file_key]
        if arr.ndim == 5:
            plane = arr[key.timepoint, key.z, key.channel]
        elif arr.ndim == 4:
            # T was squeezed (nt=1); axes are ZCYX
            plane = arr[key.z, key.channel]
        else:
            raise ValueError(f"Unexpected OME-TIFF array ndim={arr.ndim} in {fpath}")
        # np.asarray copies the slice out of the memmap so downstream code
        # can hold the data after the mmap is closed.
        return cast(np.ndarray, np.asarray(plane))
