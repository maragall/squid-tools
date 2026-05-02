# v2: Streaming Whole-Region Operations

## Purpose

v1 ships per-FOV operations and live viewer rendering with bounded RAM
(memory-bounded LRU caches, pyramid level switching, async tile loader).
v1 explicitly does **not** ship any GUI surface that loads a whole region
into memory at once — those code paths would OOM on real customer
datasets and were either deleted (`all_volumes_for_region`) or never
GUI-exposed.

v2 adds streaming/chunked equivalents so customers can run whole-region
operations on petabyte-scale acquisitions without holding the dataset in
RAM.

**Audience:** Anyone implementing whole-region rendering, fusion, or
batch processing in v2. The Algorithm Absorber when ingesting plugins
that have a region-level entry point.

**Guiding principle:** Single-FOV operations stay in RAM (cheap, fast,
already correct). Whole-region operations always stream — read tile,
process, write to disk-backed output (Zarr / OME-TIFF), drop tile.

---

## What v1 deferred (the gap to close)

### Removed in v1

- `ViewportEngine.all_volumes_for_region(channel, timepoint, level)`:
  returned `{fov_index: volume}` for every FOV in the region. On the
  10x mouse brain (~58 FOVs × 10 z × 2048² uint16 per channel) this
  would allocate ~48 GB. Not GUI-bound; deleted in v1 to remove the
  temptation. Test removed alongside.

### Restricted in v1

- `ViewportEngine.get_volume(fov, channel, ...)`: kept, but the
  docstring now states it is single-FOV only. Roughly 80 MB per call
  on real datasets. Used by `widget_3d.py` for the right-click
  "Open 3D View" feature.

### Live in v1, but limited

- `StitcherPlugin.process_region(frames, positions, params)` is the
  legacy synchronous stitcher path used only by the export-stitched-
  to-disk action. The active live-stitching path is `run_live`, which
  delegates to vendored TileFusion and scales. v2 should replace
  `process_region` callers with a streaming TileFusion pipeline that
  writes the fused output directly to a Zarr store rather than
  building it in RAM.

### 3D rendering

- v1 3D viewer (widget_3d.py) only loads the user-selected FOV. It is
  bounded (~335 MB on mouse brain when 4 channels are enabled).
  Whole-region 3D rendering — slab through a stitched mosaic — is v2.

## v2 Scope

### Streaming volume API

```python
class StreamingVolumeReader:
    """Iterator over (fov_index, channel, z, plane_array).

    Drop-in replacement for the deleted all_volumes_for_region.
    Yields one plane at a time so the caller never holds more than
    `prefetch_count` planes in RAM. Backed by the same MemoryBoundedLRUCache
    as the viewer; planes that drop out of the prefetch window are
    evicted before the next read.
    """

    def planes(
        self, channel: int, timepoint: int = 0, level: int = 0,
        prefetch_count: int = 4,
    ) -> Iterator[tuple[int, int, np.ndarray]]: ...
```

Lives on `ViewportEngine` so existing `_raw_cache` / `_processed_tile_cache`
budgets apply.

### Streaming whole-region 3D rendering

A v2 vispy `Volume` node configured for **slab streaming**:
- The node holds only the slab the user is currently viewing.
- Pan/zoom in the volume re-fetches slabs from `StreamingVolumeReader`.
- Maximum RAM ceiling = `slab_voxels × bytes_per_voxel × N_channels` —
  decoupled from total dataset size.
- GUI surface: extend the right-click menu with "Open 3D Region View…"
  alongside the existing single-FOV "Open 3D View".

### Streaming stitched export

Replace `StitcherPlugin.process_region` with a Zarr-write-through path:
- TileFusion's `fuse_to_zarr` (vendored — already supports it).
- Caller specifies an output Zarr store; tiles are read, fused, and
  written one chunk at a time.
- The synchronous in-RAM `process_region` stays as a fallback for
  small acquisitions (fits in RAM by definition) and is what existing
  unit tests assert on.

### Streaming whole-region plugin batch runs

`controller.run_plugin_region(plugin_name, region_id, output_path)`:
- Drives `StreamingVolumeReader` over every FOV.
- Calls `plugin.process(frame, params)` per tile.
- Writes processed tile to a Zarr store mirroring the input layout.
- Progress + cancel via Qt signals (separate v2 cycle for UI).

## Out of scope for v2

- GPU streaming (cupy + cuda IPC). v3 if needed.
- Cloud-backed (S3/R2) streaming reads. Today's local-disk model
  remains the v2 baseline.
- Distributed compute across machines. Single-host streaming only.

## Testing strategy

- Unit: `StreamingVolumeReader.planes` over a synthetic acquisition,
  asserting peak RAM usage ≤ `prefetch_count × plane_bytes` via
  tracemalloc snapshots.
- Integration: streaming-stitched export to a Zarr store, asserting
  the on-disk output matches the in-RAM `process_region` reference
  output bit-for-bit (or within float tolerance) on a small fixture.
- Stress: 100-FOV synthetic acquisition with 50 z-planes — must
  complete without exceeding 1 GB peak RSS.

## v1 → v2 migration notes

When v2 lands:
1. Remove the `all_volumes_for_region` deletion comment in
   `tests/unit/test_viewport_engine.py`.
2. Delete the "single-FOV only" warning in `get_volume`'s docstring
   (the streaming path is now available alongside).
3. Update `widget_3d.py` to offer the streaming whole-region option.
4. `StitcherPlugin.process_region` can either delegate to the
   Zarr-streaming path internally or stay as the small-acquisition
   shortcut — decide at v2 implementation time.
