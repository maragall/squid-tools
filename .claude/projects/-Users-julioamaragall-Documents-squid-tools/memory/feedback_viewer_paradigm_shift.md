---
name: Viewer paradigm shift - no mosaic/FOV toggle
description: The viewer is ONE continuous stage view at all zoom levels. No mode switching. Single FOV is just zoomed in. Mosaic is just zoomed out.
type: feedback
---

Critical paradigm shift from user (2026-04-10):

There is no "mosaic mode" vs "single FOV mode". There is ONE viewer that shows the stage at whatever zoom level the user wants.

**The model:**
- Zoomed out: see all tiles as thumbnails (like Google Earth seeing the whole planet)
- Zoomed in: see one tile at full resolution (like Google Earth at street level)
- Sliders (ch/z/t) work at all zoom levels
- When user clicks slider, zoom auto-adjusts to single-FOV level so they know they can navigate
- The transition is continuous, not a mode switch

**Data loading:**
- Google Maps model: only load what's in view at the current zoom level
- Zoom out: load lower-res representations
- Zoom in: load full-res for visible tiles
- All lazy, all on demand
- Pyramid of resolutions (like image-stitcher's zarr generation)

**Why:** The user said "we can't explore nor view how our processing affects our datasets." The current mode-switching paradigm breaks exploration flow. A continuous zoom allows fluid exploration.

**How to apply:**
- Kill the FOV/Mosaic toggle button
- One viewer, continuous zoom
- Study Google Maps/Earth tiling architecture
- Study Cephla-Lab/image-stitcher's zarr generation for the pyramid
- Study Cephla-Lab/ndviewer for how it navigates downsampled views
- The viewer becomes a data navigator, not a frame displayer

**Reference:** The image-stitcher generates multi-resolution zarr (OME-NGFF with pyramid levels). This IS the tile pyramid that enables Google Maps-style viewing.
