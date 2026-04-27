# OME-TIFF Reader: Squid Stitcher-Output Layout

## Purpose

Customers hand us Squid stitcher-output acquisitions where each FOV is a
multi-channel z-stack OME-TIFF in `ome_tiff/`, and acquisition metadata
ships as `acquisition parameters.json` + `configurations.xml` rather than
`acquisition.yaml`. The current `OMETiffReader.detect` requires
`acquisition.yaml`, so these datasets fail with `ValueError: No reader
found`. This is a real Squid output format we must support; it just uses
a different metadata file convention than the YAML-based one our reader
was written for.

This spec extends the existing `OMETiffReader` (no new reader subtype)
to recognize and read JSON+XML-based Squid OME-TIFF acquisitions. It also
factors out the YAML+JSON metadata loading already present in
`IndividualImageReader` so the two readers share one source of truth.

**Audience:** Anyone touching `squid_tools/core/readers/`.

**Guiding principle:** Same format, same on-disk frames, same
`Acquisition` dataclass — only the metadata source differs. The reader
should accept any combination of (yaml | json) plus an optional XML
channel manifest, falling back gracefully across them.

---

## Current state

- `OMETiffReader.detect` (`squid_tools/core/readers/ome_tiff.py:36`): hard
  requires `acquisition.yaml`.
- `OMETiffReader.read_metadata` (line 42): opens `acquisition.yaml`
  unconditionally, then optionally enriches from
  `acquisition parameters.json` for `sensor_pixel_size_um` /
  `tube_lens_mm`. Channels come from YAML only.
- `IndividualImageReader.read_metadata` (`individual.py:52`): already
  handles YAML + JSON together with proper fallbacks for objective,
  z-stack, time-series; auto-detects channels from filename suffixes.
- `configurations.xml` is read by **neither** reader today.

## What we're changing

### Shared metadata helper

New module `squid_tools/core/readers/_squid_metadata.py` exposes:

```python
def load_yaml_and_json(path: Path) -> tuple[dict, dict]:
    """Return (yaml_meta, json_params). Either may be empty."""

def parse_channels_from_xml(xml_path: Path) -> list[AcquisitionChannel]:
    """Return channels for every <mode Selected=\"true\"> entry."""

def build_objective_from(
    yaml_meta: dict, json_params: dict,
) -> ObjectiveMetadata: ...

def build_z_stack_from(
    yaml_meta: dict, json_params: dict,
) -> ZStackConfig | None: ...

def build_time_series_from(
    yaml_meta: dict, json_params: dict,
) -> TimeSeriesConfig | None: ...

def build_mode_from(yaml_meta: dict) -> AcquisitionMode: ...

def build_scan_from(yaml_meta: dict) -> ScanConfig: ...
```

The first three (`load_yaml_and_json`, `parse_channels_from_xml`,
`build_objective_from`) are new. The last four extract logic that already
exists in `IndividualImageReader.read_metadata` so both readers share
one implementation.

### `OMETiffReader.detect`

```python
@classmethod
def detect(cls, path: Path) -> bool:
    ome_dir = path / "ome_tiff"
    if not (ome_dir.is_dir() and any(ome_dir.glob("*.ome.tiff"))):
        return False
    has_yaml = (path / "acquisition.yaml").exists()
    has_json = (path / "acquisition parameters.json").exists()
    return has_yaml or has_json
```

### `OMETiffReader.read_metadata`

Rewritten to use the shared helpers:

```python
def read_metadata(self, path: Path) -> Acquisition:
    self._path = path
    yaml_meta, json_params = load_yaml_and_json(path)

    objective = build_objective_from(yaml_meta, json_params)

    # Channels: YAML first, then XML, then empty.
    channels: list[AcquisitionChannel] = []
    if yaml_meta.get("channels"):
        channels = [_channel_from_yaml(c) for c in yaml_meta["channels"]]
    elif (path / "configurations.xml").exists():
        channels = parse_channels_from_xml(path / "configurations.xml")

    mode = build_mode_from(yaml_meta)
    scan = build_scan_from(yaml_meta)
    z_stack = build_z_stack_from(yaml_meta, json_params)
    time_series = build_time_series_from(yaml_meta, json_params)
    regions = self._parse_regions_from_files(path, yaml_meta)

    return Acquisition(
        path=path, format=AcquisitionFormat.OME_TIFF, mode=mode,
        objective=objective, channels=channels, scan=scan,
        z_stack=z_stack, time_series=time_series, regions=regions,
    )
```

`_channel_from_yaml` is local; nothing else changes in
`_parse_regions_from_files` or `read_frame`.

### `IndividualImageReader.read_metadata`

Refactored to use the same helpers. Behavior unchanged — this is a
shape-preserving simplification that removes the duplicated metadata
parsing logic.

### `parse_channels_from_xml` semantics

Input: a Squid `configurations.xml` like:

```xml
<modes>
  <mode ID="5" Name="Fluorescence 405 nm Ex"
        ExposureTime="50.0" IlluminationSource="11"
        IlluminationIntensity="21.0"
        Selected="true">2141688</mode>
  <mode ID="1" Name="BF LED matrix full"
        ExposureTime="12.0" Selected="false">16777215</mode>
  ...
</modes>
```

Output: one `AcquisitionChannel` per `<mode Selected="true">` element, in
document order. Field mapping:

- `name` ← `Name` attribute
- `illumination_source` ← `IlluminationSource` attribute (string)
- `illumination_intensity` ← float(`IlluminationIntensity`)
- `exposure_time_ms` ← float(`ExposureTime`)
- `z_offset_um` ← float(`ZOffset`) if present, else 0.0

Anything not marked `Selected="true"` is ignored (matches Squid's "active
modes" semantics — those are the channels that were actually acquired).

## Edge cases

- **No YAML, no JSON, no XML:** `detect()` already returns False (the
  `has_yaml or has_json` guard catches this). No change needed.
- **YAML with channels, XML also present:** YAML wins (it's the canonical
  source when present). XML is fallback only.
- **XML with no `Selected="true"` modes:** returns empty channel list.
  The reader returns the `Acquisition` with zero channels; downstream
  code in `viewport_engine.compute_contrast` already handles
  `active_channels=[]` (early-return `[]`), so the GUI shows an empty
  canvas rather than crashing.
- **Coordinates in `coordinates.csv` at root vs `0/coordinates.csv`:**
  `_parse_regions_from_files` already tries both paths.
- **Mixed datasets (both YAML and JSON+XML present):** YAML+JSON merge
  per existing fallback logic; XML is unused (YAML channels win).

## Testing

New file `tests/unit/test_squid_metadata.py`:

- **`test_parse_channels_from_xml_selected_only`**: synthetic XML with
  three modes (two `Selected="true"`, one `Selected="false"`). Assert
  exactly the two selected channels are returned, in document order,
  with correct attribute values.
- **`test_parse_channels_from_xml_empty`**: XML with no selected modes →
  empty list.
- **`test_load_yaml_and_json_yaml_only`**: tmp dir with only
  `acquisition.yaml` → returns `(yaml_meta, {})`.
- **`test_load_yaml_and_json_json_only`**: tmp dir with only
  `acquisition parameters.json` → returns `({}, json_params)`.
- **`test_load_yaml_and_json_both`**: both files → both dicts populated.

Update `tests/unit/test_readers_ome_tiff.py` (or create if missing):

- **`test_ome_tiff_detect_with_yaml`**: existing fixture still detected.
- **`test_ome_tiff_detect_with_json_xml_no_yaml`**: synthesize a tiny
  Squid stitcher-output layout (one tiny ome.tiff, JSON, XML, coords)
  and assert `OMETiffReader.detect()` returns True.
- **`test_ome_tiff_read_metadata_json_xml`**: read the synthetic dataset
  and assert channels (from XML), objective (from JSON), z-stack (from
  JSON Nz/dz) populate correctly.

Update `tests/unit/test_readers_individual.py` if it asserts specific
implementation details — the metadata-loading paths are now shared so
behavior should be identical, but a refactor-shape test may need
adjusting.

Manual GUI verification: launch on the Spencer-feedback dataset
(`/Users/julioamaragall/Downloads/Spencer-Feedback-ndviewer_light-stitcher/test_10x_laser_af_z_stack_2025-10-28_13-40-43.939945 yy`)
and confirm the GUI loads, channels appear (405, 488, 561, 638), and
the contrast fix from the cache-split refactor still behaves (no
oscillation, stable across zoom).

## Out of scope

- Any change to OME-TIFF frame loading (`read_frame`).
- Any change to the cache-split refactor.
- Any change to readers' `detect` priority order.
- Adding a new format type or new reader class.
