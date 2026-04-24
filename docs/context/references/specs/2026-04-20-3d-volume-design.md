# 3D Volume Rendering Design Spec

## Purpose

The 2D viewer shows a plane at a time. A Z-stack acquisition captures a depth-stack of planes per FOV, and users need to see the volume — especially for tissue samples and spheroids. This cycle lays the foundation for 3D rendering:

1. A volume-fetching path in the engine (`get_volume`) that stacks Z planes into a 3D array
2. A multi-channel volume compositor (pure-numpy RGBA output, GPU variant deferred)
3. A `Volume3DCanvas` that wraps `vispy.scene.visuals.Volume` with a turntable camera

**NOT in this cycle:** full `Viewer3DWidget` integration, live Z-stack navigation sliders in 3D, 3D FOV selection, 3D processing pipelines. Those require the GUI threading audit pending for Cycle C. We ship the primitives so a user (or a future cycle) can assemble them.

**Audience:** Users with Z-stacks (tissue, spheroids). After this cycle, anyone can run a small script that loads an acquisition, asks the engine for a volume, hands it to a `Volume3DCanvas`, and sees a rotatable ray-marched view.

**Guiding principle:** Build the pipeline end-to-end headless-testable. GUI integration comes in a later cycle once the async-loader teardown story is solid.

---

## Scope

**IN:**
- `ViewportEngine.get_volume(fov, channel, timepoint, level=0) -> np.ndarray` returning `(Z, Y, X)` — stacks Z planes using `_get_pyramid` per plane
- `ViewportEngine.all_volumes_for_region(channel, timepoint, level=0) -> dict[int, np.ndarray]` returning one volume per FOV in the current region
- `compositor.composite_volume_channels(volumes, clims, colors_rgb) -> np.ndarray` returning `(Z, Y, X, 4)` RGBA float32 (alpha = max over channels, for ray-marched transparency)
- `squid_tools/viewer/volume_canvas.py` with `Volume3DCanvas` wrapping `vispy.scene.SceneCanvas` + `scene.visuals.Volume` + `cameras.TurntableCamera`
- `Volume3DCanvas.set_volume(rgba_volume, voxel_size_um)` — uploads the RGBA volume to the GPU, sets camera FOV to fit
- Headless tests: `Volume3DCanvas` instantiates and `set_volume` doesn't crash with small synthetic volumes (32x32x32)

**OUT (future cycles):**
- `Viewer3DWidget` / Qt integration (interaction, mouse drag, sliders for time/channel in 3D)
- GPU-side ray marching (vispy's built-in Volume visual already does ray marching; we delegate to it)
- GLSL fragment-shader custom compositing (vispy handles transfer functions on device)
- 3D FOV selection, 3D processing pipelines
- Multi-resolution volume streaming (volumes come back at pyramid level 0 for now; `level` parameter is plumbed for future use)
- Saving 3D views to image

---

## Architecture

```
User script (future cycle will wrap this in a Widget):

engine = ViewportEngine()
engine.load(path, region_id)

# Option 1: one volume per FOV
volumes_by_fov = engine.all_volumes_for_region(channel=0, timepoint=0)

# Option 2: multi-channel composite of a single FOV
vols = [engine.get_volume(fov=0, channel=c, timepoint=0) for c in (0, 1)]
clims = [(0.0, 1.0), (0.0, 1.0)]
colors = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
rgba = composite_volume_channels(vols, clims, colors)  # (Z, Y, X, 4)

canvas = Volume3DCanvas()
canvas.set_volume(rgba, voxel_size_um=(pixel_size_xy, pixel_size_xy, z_step_um))
canvas.native_widget().show()  # (or embed in a Qt layout)
```

---

## Components

### 1. `ViewportEngine.get_volume`

```python
def get_volume(
    self, fov: int, channel: int, timepoint: int = 0, level: int = 0,
) -> np.ndarray:
    """Return the Z-stack for (fov, channel, timepoint) as (Z, Y, X)."""
    if self._acquisition is None:
        raise RuntimeError("No acquisition loaded")
    z_stack = self._acquisition.z_stack
    nz = z_stack.nz if z_stack else 1
    planes = [
        self._get_pyramid(fov, z, channel, timepoint, level)
        for z in range(nz)
    ]
    return np.stack(planes, axis=0)
```

Stored attribute: the engine already keeps the acquisition. Check the exact attribute name during implementation.

### 2. `ViewportEngine.all_volumes_for_region`

```python
def all_volumes_for_region(
    self, channel: int, timepoint: int = 0, level: int = 0,
) -> dict[int, np.ndarray]:
    """Return {fov_index: volume} for every FOV in the current region."""
    if self._index is None:
        return {}
    return {
        fov.fov_index: self.get_volume(fov.fov_index, channel, timepoint, level)
        for fov in self._index.all()
    }
```

If `_index.all()` doesn't exist, use whichever API enumerates FOVs (e.g. `_index.query(*self.bounding_box())`).

### 3. `compositor.composite_volume_channels`

Same mechanics as `composite_channels` but operates on 3D arrays. Returns RGBA:

```python
def composite_volume_channels(
    volumes: Sequence[np.ndarray],
    clims: Sequence[tuple[float, float]],
    colors_rgb: Sequence[tuple[float, float, float]],
    backend: Backend | None = None,
) -> np.ndarray:
    """Composite N 3D grayscale volumes into (Z, Y, X, 4) float32 RGBA.

    RGB is the usual additive composite (sum of color * normalized,
    clipped). Alpha is the per-voxel max normalized value across
    channels (so blank voxels stay transparent in ray marching).
    """
```

Validation mirrors `composite_channels`: at least one channel, matching length, all 3D, same shape. Numpy-only this cycle; `backend` parameter reserved for a future CuPy implementation.

### 4. `Volume3DCanvas`

```python
# squid_tools/viewer/volume_canvas.py
"""3D volume canvas: vispy Volume visual + TurntableCamera."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import vispy.scene
from vispy.scene import SceneCanvas
from vispy.scene.cameras import TurntableCamera
from vispy.scene.visuals import Volume

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class Volume3DCanvas:
    """Headless-safe 3D volume canvas.

    wraps vispy.SceneCanvas + scene.visuals.Volume. Does not assume a
    Qt parent, so tests can instantiate without a QApplication (vispy
    falls back to its null backend in that case).
    """

    def __init__(self, size: tuple[int, int] = (600, 600)) -> None:
        self._canvas = SceneCanvas(keys="interactive", size=size, show=False)
        self._view = self._canvas.central_widget.add_view()
        self._view.camera = TurntableCamera(
            fov=45, azimuth=30, elevation=30, distance=3.0,
        )
        self._volume_visual: Volume | None = None

    def native_widget(self) -> object:
        return self._canvas.native

    def set_volume(
        self, rgba_volume: np.ndarray, voxel_size_um: tuple[float, float, float],
    ) -> None:
        """Upload an (Z, Y, X, 4) RGBA float32 volume to the canvas.

        voxel_size_um = (vx, vy, vz) is used to scale the displayed
        volume so the aspect ratio matches physical space.
        """
        if rgba_volume.ndim != 4 or rgba_volume.shape[-1] != 4:
            raise ValueError(
                f"rgba_volume must be (Z, Y, X, 4), got {rgba_volume.shape}",
            )
        if self._volume_visual is not None:
            self._volume_visual.parent = None
        self._volume_visual = Volume(
            rgba_volume, parent=self._view.scene,
            method="translucent",
        )
        # Scale the visual so each voxel's extent matches voxel_size_um
        vx, vy, vz = voxel_size_um
        self._volume_visual.transform = vispy.scene.transforms.STTransform(
            scale=(vx, vy, vz),
        )
        self._canvas.update()

    def close(self) -> None:
        self._canvas.close()
```

---

## Data Flow

1. `engine.get_volume(fov, channel, timepoint, level=0)` → for each z in [0, nz), call `_get_pyramid(fov, z, channel, timepoint, level)`, stack with `np.stack`.
2. For multi-channel display: call `get_volume` for each channel, then `composite_volume_channels(volumes, clims, colors)` → `(Z, Y, X, 4)` float32.
3. `canvas.set_volume(rgba_volume, voxel_size_um)` uploads to GPU via vispy's `Volume` visual; vispy's built-in ray marcher handles the rendering.

---

## Error Handling

| Failure | Behavior |
|---------|----------|
| `get_volume` called with no acquisition loaded | Raises `RuntimeError("No acquisition loaded")` |
| `get_volume` for an FOV / channel that doesn't exist | Propagates the reader's error (`ValueError` etc.) |
| `composite_volume_channels` with empty / mismatched input | Raises `ValueError` (same contract as `composite_channels`) |
| `Volume3DCanvas.set_volume` with wrong-shape array | Raises `ValueError` |
| vispy fails to create a GL context (no display) | vispy falls back to "null" backend; `set_volume` still works for data upload but the actual render is a no-op. Tests run in this mode. |

---

## UX Details

None user-facing this cycle — this is primitive construction. The next cycle (Cycle C completion + 3D widget) will wire this into a Qt widget.

Log output at INFO:
```
[14:23:00] [INFO] [viewer] volume composited: (32, 128, 128, 4) from 2 channels
```

(Emitted once per composite call at INFO.)

---

## Testing Plan

**(Written at end of all cycles — functional user workflow tests for the complete integrated product. Per-cycle TDD is handled by superpowers during implementation.)**

Placeholder: this cycle's TDD tests live in its implementation plan. The spec's Testing Plan section will be written when all planned cycles are complete, describing end-to-end user workflows to validate the full product.
