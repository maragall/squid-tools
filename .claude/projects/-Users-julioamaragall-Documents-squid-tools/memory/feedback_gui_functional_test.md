---
name: GUI functional test feedback (2026-04-10)
description: Critical feedback from first functional test with real 10x mouse brain data. Major issues with viewer, styling, and layout.
type: feedback
---

Functional test with real Squid data (10x_mouse_brain, 70 FOVs, 4 channels, region="manual"):

**Viewer issues:**
- Mosaic to single FOV transition not centered on the clicked tile
- Sliders not working (channel/z/t sliders don't update the display)
- No FOV slider (need to navigate between FOVs in single FOV mode)
- Tiles should overlap based on coordinates.csv positions (stage motor imprecision causes misalignment, that's expected and should be visible)

**Styling issues:**
- Color palette doesn't look good in practice (user said "I don't like the color")
- Too much spacing in layout
- Sliders look bad
- Does not look like NIS Elements, Revvity Harmony, or Araceli HCS viewer

**Why:** The current implementation is a skeleton. The vispy viewer was built without visual reference to commercial products. The QSS stylesheet was written without seeing it on screen.

**How to apply:**
- Study actual screenshots of NIS Elements, Revvity Harmony, Araceli Endeavor before writing GUI code
- Test with real data (not just synthetic fixtures) during development
- The viewer needs to be rebuilt with proper commercial-grade UX
- Fix slider wiring, FOV navigation, mosaic centering as priority bugs
- The styling needs to be iterated on with the GUI visible, not written blind
