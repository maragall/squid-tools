"""3D volume canvas: vispy Volume visual + TurntableCamera.

Wraps vispy's Volume visual for ray-marched display of a scalar 3D
array. Multi-channel composite visualization is done per-channel
(one Volume per channel, blended by vispy). Pre-computed RGBA volumes
from `compositor.composite_volume_channels` can be displayed via
`set_rgba_volume`, which adds one Volume per color channel.
"""

from __future__ import annotations

import contextlib
import logging

import numpy as np
import vispy.scene
from vispy.scene import SceneCanvas
from vispy.scene.cameras import TurntableCamera
from vispy.scene.visuals import Volume

logger = logging.getLogger(__name__)


class Volume3DCanvas:
    """3D volume canvas backed by vispy Volume + turntable camera."""

    def __init__(self, size: tuple[int, int] = (600, 600)) -> None:
        self._canvas = SceneCanvas(keys="interactive", size=size, show=False)
        self._view = self._canvas.central_widget.add_view()
        self._view.camera = TurntableCamera(
            fov=45, azimuth=30, elevation=30, distance=3.0,
        )
        self._volume_visuals: list[Volume] = []

    def native_widget(self) -> object:
        """Return vispy's native (Qt) widget for embedding."""
        return self._canvas.native

    def _clear_visuals(self) -> None:
        for v in self._volume_visuals:
            v.parent = None
        self._volume_visuals.clear()

    def set_volume(
        self,
        volume: np.ndarray,
        voxel_size_um: tuple[float, float, float],
        clim: tuple[float, float] | str = "auto",
        cmap: str = "grays",
    ) -> None:
        """Upload a 3D scalar volume.

        volume: (Z, Y, X) float or integer array.
        voxel_size_um: (vx, vy, vz) in micrometers to scale physically.
        clim: contrast limits, or "auto".
        cmap: vispy colormap name (grays, viridis, hot, etc.).
        """
        if volume.ndim != 3:
            raise ValueError(
                f"volume must be (Z, Y, X), got shape {volume.shape}",
            )
        self._clear_visuals()
        visual = Volume(
            volume, parent=self._view.scene,
            method="translucent", clim=clim, cmap=cmap,
        )
        vx, vy, vz = voxel_size_um
        visual.transform = vispy.scene.transforms.STTransform(
            scale=(vx, vy, vz),
        )
        self._volume_visuals.append(visual)
        self._frame_volume(volume.shape, voxel_size_um)
        logger.info(
            "Volume3DCanvas.set_volume uploaded shape=%s voxel=%s",
            volume.shape, voxel_size_um,
        )

    def set_channel_volumes(
        self,
        volumes: list[np.ndarray],
        clims: list[tuple[float, float]],
        cmaps: list[str],
        voxel_size_um: tuple[float, float, float],
    ) -> None:
        """Upload N scalar volumes, each with its own colormap.

        vispy layers them with additive blending via the "translucent"
        method, approximating a multi-channel composite in 3D.
        """
        if not (len(volumes) == len(clims) == len(cmaps)):
            raise ValueError("volumes, clims, cmaps must be same length")
        if not volumes:
            raise ValueError("at least one volume required")
        shape = volumes[0].shape
        for v in volumes[1:]:
            if v.shape != shape:
                raise ValueError("all volumes must have the same shape")

        self._clear_visuals()
        vx, vy, vz = voxel_size_um
        for vol, clim, cmap in zip(volumes, clims, cmaps, strict=True):
            visual = Volume(
                vol, parent=self._view.scene,
                method="translucent", clim=clim, cmap=cmap,
            )
            visual.transform = vispy.scene.transforms.STTransform(
                scale=(vx, vy, vz),
            )
            self._volume_visuals.append(visual)
        self._frame_volume(shape, voxel_size_um)
        logger.info(
            "Volume3DCanvas.set_channel_volumes uploaded %d channels shape=%s",
            len(volumes), shape,
        )

    def _frame_volume(
        self,
        shape: tuple[int, ...],
        voxel_size_um: tuple[float, float, float],
    ) -> None:
        z, h, w = shape[:3]
        vx, vy, vz = voxel_size_um
        self._view.camera.set_range(
            x=(0.0, w * vx),
            y=(0.0, h * vy),
            z=(0.0, z * vz),
        )
        self._canvas.update()

    def close(self) -> None:
        """Release the canvas; safe to call multiple times."""
        with contextlib.suppress(Exception):
            self._canvas.close()
