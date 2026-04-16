---
name: Viewer polish feedback round 2 (2026-04-10)
description: Continuous viewer working but has contrast/channel/background issues during zoom and channel switching
type: feedback
---

The continuous viewer is working and the user is excited. Issues to fix:

1. **Channel color sticks on old tiles**: Zoom in, change channel (e.g., 405 blues -> 488 greens), zoom out. The tiles that were already rendered outside the viewport still show the old channel color. Only newly loaded tiles show the new channel.

2. **Background is white, should be black**: The canvas background color needs to be #1a1a1a or black. Microscopy data on white background looks wrong.

3. **Contrast inconsistency across zoom levels**: When zooming in/out, tiles loaded at different times may have different contrast stats applied if the clim was recomputed between loads.

**Why:** The render_tiles() method only updates VISIBLE tiles. When the user changes channel and zooms out, previously rendered tiles outside the viewport weren't cleared. They still show the old channel data.

**Fix approach:**
- On channel/slider change: clear ALL tiles (not just update visible ones), then refresh
- Set canvas background to black
- Recompute contrast once per channel change, apply globally to all tiles including new ones
