---
name: Squid-Tools Project Context
description: Key architectural decisions and constraints for squid-tools microscopy post-processing suite
type: project
---

**Core modules (cycle 1):** Viewer (ndviewer_light), Stitching (maragall/stitcher), Deconvolution (PetaKit), Background Subtraction (sep), Flatfield Correction (BasicPy). Denoising shelved (aCNS analytical for later). Phase from defocus: later.

**Why:** Cephla-Lab/Squid needs a unified post-processing companion that reads Squid formats and is distributable as .exe (Windows) and .AppImage (Linux).

**How to apply:**
- Connector architecture — wraps best-known implementations
- Checkbox install menu: user picks which modules to install
- Shared data model built from Squid's writers (OME-TIFF, Individual Images, Zarr)
- Multi-page TIFF discontinued — 3 formats: OME_TIFF, INDIVIDUAL_IMAGES, ZARR
- OME metadata standardization critical — collaborate with Media Cybernetics
- Architecture B: Core library (zero GUI deps) + thin PyQt5 shell + plugin ABC
- Mosaic: napari + dask.array + tifffile (proven library, not custom)
- GUI: dock-widget panels (Napari), well plate grid (NIS/Harmony), right-click + double-click nested menus (NIS), layer-based results, tooltips everywhere
- Live transforms: Option B — click Run, see result as new layer
- FOV borders: Shapes layer overlay, color-coded, intersection/overlap highlighting
- Sidecar: lightweight manifest + lazy refs, no data duplication
- No time estimates — cycles are per-task
- Pattern reference: Cephla-Lab/image-stitcher early commits (pydantic, ruff, mypy, ABC loaders)
- maragall/stitcher is the SHIPPING stitcher, image-stitcher is pattern reference only
- Next cycles: cell tracking, Smart Acquisition (CRUK 3D), aCNS denoising, phase from defocus
- Image downsampler NOT needed — Squid embeds downsampled images in metadata
- Stitcher needs OME-TIFF export
- MCP API server deferred to cycle 2
