"""Shared metadata loading for Squid acquisition formats.

Squid acquisitions ship metadata in any combination of:

- ``acquisition.yaml`` — the canonical, full-fidelity manifest.
- ``acquisition parameters.json`` — a lighter-weight Squid-software dump
  with grid dims, z-stack params, and objective info.
- ``configurations.xml`` — Squid's "modes" file. Each ``<mode>`` element
  describes an acquisition channel; only those with ``Selected="true"``
  are channels that were actually captured.

Different Squid software versions and output paths emit different
combinations. The helpers here let the format readers (OME-TIFF and
INDIVIDUAL_IMAGES today) parse whatever combination is present.

See ``docs/superpowers/specs/2026-04-26-ome-tiff-reader-squid-output-design.md``.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

from squid_tools.core.data_model import (
    AcquisitionChannel,
    AcquisitionMode,
    ObjectiveMetadata,
    ScanConfig,
    TimeSeriesConfig,
    ZStackConfig,
)


def load_yaml_and_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(yaml_meta, json_params)``. Either may be empty."""
    yaml_meta: dict[str, Any] = {}
    yaml_path = path / "acquisition.yaml"
    if yaml_path.exists():
        with open(yaml_path) as f:
            yaml_meta = yaml.safe_load(f) or {}

    json_params: dict[str, Any] = {}
    json_path = path / "acquisition parameters.json"
    if json_path.exists():
        with open(json_path) as f:
            json_params = json.load(f)

    return yaml_meta, json_params


def parse_channels_from_xml(xml_path: Path) -> list[AcquisitionChannel]:
    """Return one ``AcquisitionChannel`` per ``<mode Selected="true">``.

    Modes not marked selected are ignored — they correspond to Squid
    illumination configurations that exist on the system but were not
    used in this acquisition.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    channels: list[AcquisitionChannel] = []
    for mode in root.findall("mode"):
        if (mode.get("Selected") or "").lower() != "true":
            continue
        channels.append(AcquisitionChannel(
            name=mode.get("Name", ""),
            illumination_source=mode.get("IlluminationSource", ""),
            illumination_intensity=float(mode.get("IlluminationIntensity", 0.0)),
            exposure_time_ms=float(mode.get("ExposureTime", 0.0)),
            z_offset_um=float(mode.get("ZOffset", 0.0)),
        ))
    return channels


def channel_from_yaml(ch: dict[str, Any]) -> AcquisitionChannel:
    """Build an ``AcquisitionChannel`` from a YAML channel dict."""
    illum = ch.get("illumination_settings", {})
    cam = ch.get("camera_settings", {})
    return AcquisitionChannel(
        name=ch.get("name", ""),
        illumination_source=illum.get("illumination_channel", ""),
        illumination_intensity=illum.get("intensity", 0.0),
        exposure_time_ms=cam.get("exposure_time_ms", 0.0),
        z_offset_um=ch.get("z_offset_um", 0.0),
    )


def build_objective(
    yaml_meta: dict[str, Any], json_params: dict[str, Any],
) -> ObjectiveMetadata:
    """Build ObjectiveMetadata, preferring YAML and falling back to JSON."""
    obj_meta = yaml_meta.get("objective", {})
    obj_json = json_params.get("objective", {})
    magnification = obj_meta.get("magnification") or obj_json.get("magnification", 1.0)
    sensor_px = json_params.get("sensor_pixel_size_um", 7.52)
    tube_lens_mm = json_params.get("tube_lens_mm", 180.0)
    tube_lens_f = obj_json.get("tube_lens_f_mm", tube_lens_mm)
    pixel_size = obj_meta.get("pixel_size_um") or (sensor_px / magnification)

    return ObjectiveMetadata(
        name=obj_meta.get("name") or obj_json.get("name", "unknown"),
        magnification=magnification,
        pixel_size_um=pixel_size,
        numerical_aperture=obj_json.get("NA"),
        sensor_pixel_size_um=sensor_px,
        tube_lens_mm=tube_lens_mm,
        tube_lens_f_mm=tube_lens_f,
    )


def build_z_stack(
    yaml_meta: dict[str, Any], json_params: dict[str, Any],
) -> ZStackConfig | None:
    """Build a ZStackConfig from YAML/JSON, or None when no z-stack present."""
    zs_meta = yaml_meta.get("z_stack", {})
    nz = zs_meta.get("nz") or json_params.get("Nz", 0)
    if nz <= 0:
        return None
    dz_mm = zs_meta.get("delta_z_mm") or (json_params.get("dz(um)", 1.5) / 1000)
    direction = (
        "FROM_BOTTOM"
        if zs_meta.get("config", "FROM_BOTTOM") == "FROM_BOTTOM"
        else "FROM_TOP"
    )
    return ZStackConfig(
        nz=nz,
        delta_z_mm=dz_mm,
        direction=direction,
        use_piezo=zs_meta.get("use_piezo", False),
    )


def build_time_series(
    yaml_meta: dict[str, Any], json_params: dict[str, Any],
) -> TimeSeriesConfig | None:
    """Build a TimeSeriesConfig from YAML/JSON, or None when nt<=0."""
    ts_meta = yaml_meta.get("time_series", {})
    nt = ts_meta.get("nt") or json_params.get("Nt", 0)
    if nt <= 0:
        return None
    dt_s = ts_meta.get("delta_t_s") or json_params.get("dt(s)", 0.0)
    return TimeSeriesConfig(nt=nt, delta_t_s=dt_s)


def build_mode(yaml_meta: dict[str, Any]) -> AcquisitionMode:
    """Resolve AcquisitionMode from YAML widget_type, default MANUAL."""
    widget_type = yaml_meta.get("acquisition", {}).get("widget_type", "")
    if widget_type in ("wellplate", "flexible"):
        return AcquisitionMode(widget_type)
    return AcquisitionMode.MANUAL


def build_scan(yaml_meta: dict[str, Any]) -> ScanConfig:
    """Resolve ScanConfig overlap from YAML wellplate/flexible scan dicts."""
    if "wellplate_scan" in yaml_meta:
        return ScanConfig(
            overlap_percent=yaml_meta["wellplate_scan"].get("overlap_percent"),
        )
    if "flexible_scan" in yaml_meta:
        return ScanConfig(
            overlap_percent=yaml_meta["flexible_scan"].get("overlap_percent"),
        )
    return ScanConfig()
