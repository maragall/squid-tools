"""Viewer3DWidget — Qt wrapper around Volume3DCanvas.

Opens from the 2D viewer's right-click menu ("Open 3D View…"). Shows
the selected FOV's z-stack as a rotatable volume. Multi-channel mode
layers one Volume visual per channel (vispy translucent additive
blending). Close button releases the GL canvas.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from squid_tools.viewer.viewport_engine import ViewportEngine
from squid_tools.viewer.volume_canvas import Volume3DCanvas

logger = logging.getLogger(__name__)


class Viewer3DWidget(QWidget):
    """Dockable / standalone 3D viewer.

    Owns one Volume3DCanvas and a small control row (FOV spin, channel
    toggles, refresh, close). Built against a ViewportEngine that's
    already loaded the acquisition.
    """

    def __init__(
        self,
        engine: ViewportEngine,
        channel_names: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._channel_names = channel_names

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Control row
        ctl_row = QHBoxLayout()
        ctl_row.addWidget(QLabel("FOV"))
        self._fov_spin = QSpinBox()
        fov_indices = sorted(engine.all_fov_indices())
        if fov_indices:
            self._fov_spin.setRange(min(fov_indices), max(fov_indices))
            self._fov_spin.setValue(fov_indices[0])
        else:
            self._fov_spin.setRange(0, 0)
        ctl_row.addWidget(self._fov_spin)

        self._channel_checks: list[QCheckBox] = []
        for name in channel_names:
            short = name
            for pat in ("405", "488", "561", "638", "730"):
                if pat in name:
                    short = f"{pat}nm"
                    break
            cb = QCheckBox(short)
            cb.setChecked(True)
            cb.setToolTip(name)
            ctl_row.addWidget(cb)
            self._channel_checks.append(cb)

        refresh_btn = QPushButton("Load")
        refresh_btn.setToolTip("Load the selected FOV + channels as a 3D volume.")
        refresh_btn.clicked.connect(self._reload_volume)
        ctl_row.addWidget(refresh_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        ctl_row.addWidget(close_btn)

        ctl_row.addStretch()
        layout.addLayout(ctl_row)

        # Canvas
        self._canvas = Volume3DCanvas(size=(800, 600))
        native = self._canvas.native_widget()
        if native is not None:
            layout.addWidget(native, stretch=1)  # type: ignore[arg-type]

        self.setWindowTitle("Squid-Tools 3D")
        self.resize(900, 700)
        self._reload_volume()

    def _reload_volume(self) -> None:
        """Fetch volumes for the selected FOV + enabled channels, upload."""
        if self._engine is None:
            return
        fov = self._fov_spin.value()
        enabled = [i for i, cb in enumerate(self._channel_checks) if cb.isChecked()]
        if not enabled:
            logger.info("Viewer3DWidget: no channels enabled; skipping load.")
            return
        try:
            volumes = [
                self._engine.get_volume(fov=fov, channel=c, timepoint=0)
                for c in enabled
            ]
        except Exception:
            logger.exception("Viewer3DWidget: failed to load volume")
            return
        clims = [(float(v.min()), float(v.max())) for v in volumes]
        cmaps = ["reds", "greens", "blues", "hot", "viridis", "plasma"][: len(volumes)]
        if len(volumes) == 1:
            self._canvas.set_volume(
                volumes[0],
                voxel_size_um=self._engine.voxel_size_um(),
                clim=clims[0],
                cmap=cmaps[0] if cmaps else "grays",
            )
        else:
            self._canvas.set_channel_volumes(
                volumes=volumes,
                clims=clims,
                cmaps=cmaps,
                voxel_size_um=self._engine.voxel_size_um(),
            )
        logger.info(
            "Viewer3DWidget loaded fov=%d channels=%s", fov, enabled,
        )

    def closeEvent(self, event: object) -> None:  # noqa: N802
        try:
            self._canvas.close()
        finally:
            super().closeEvent(event)  # type: ignore[arg-type]
