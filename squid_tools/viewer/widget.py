"""Continuous zoom stage viewer.

One viewer. No mode switching. Zoom controls resolution.
Pan loads new tiles on demand. Sliders work at every zoom level.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from squid_tools.viewer.canvas import StageCanvas
from squid_tools.viewer.selection import SelectionState
from squid_tools.viewer.tile_loader import AsyncTileLoader
from squid_tools.viewer.viewport_engine import ViewportEngine


class ViewerWidget(QWidget):
    """Continuous zoom stage viewer."""

    fov_clicked = Signal(str, int)  # region_id, fov_index

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._canvas = StageCanvas()
        self._engine = ViewportEngine()
        self._region: str = ""
        self._channels: list[str] = []

        self._tile_loader: AsyncTileLoader | None = None
        self._last_applied_id: int = 0

        self.selection = SelectionState(self)
        self._canvas.selection_drawn.connect(self._on_selection_drawn)
        self.selection.selection_changed.connect(self._on_selection_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        native = self._canvas.native_widget()
        if native is not None:
            layout.addWidget(native, stretch=1)  # type: ignore[arg-type]

        # Sliders
        # Channel toggles row (per-channel on/off for composite)
        from PySide6.QtWidgets import QCheckBox
        self._channel_row = QHBoxLayout()
        self._channel_row.setContentsMargins(4, 2, 4, 2)
        self._channel_checkboxes: list[QCheckBox] = []
        # Populated in load_acquisition when channels are known
        layout.addLayout(self._channel_row)

        # Z and T sliders
        slider_row = QHBoxLayout()
        slider_row.setContentsMargins(4, 2, 4, 2)

        slider_row.addWidget(QLabel("Z"))
        self.z_slider = QSlider(Qt.Orientation.Horizontal)
        self.z_slider.setRange(0, 0)
        self.z_slider.setToolTip("Z-level")
        self.z_slider.valueChanged.connect(self._on_slider_changed)
        slider_row.addWidget(self.z_slider)

        slider_row.addWidget(QLabel("T"))
        self.t_slider = QSlider(Qt.Orientation.Horizontal)
        self.t_slider.setRange(0, 0)
        self.t_slider.setToolTip("Timepoint")
        self.t_slider.valueChanged.connect(self._on_slider_changed)
        slider_row.addWidget(self.t_slider)

        layout.addLayout(slider_row)

        # Keep channel_slider as a hidden attribute for backward compat with tests
        self.channel_slider = QSlider(Qt.Orientation.Horizontal)
        self.channel_slider.setRange(0, 0)

        # Debounce timer for viewport changes (pan/zoom)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(50)  # 50ms debounce
        self._refresh_timer.timeout.connect(self._refresh)

        # Connect to canvas draw event for viewport-driven loading
        self._canvas.connect_draw(self._on_draw)

    def load_acquisition(self, path: Path, region: str = "0") -> None:
        """Load acquisition and display the stage view."""
        from squid_tools.core.readers import detect_reader

        reader = detect_reader(path)
        acq = reader.read_metadata(path)

        self._engine.load(path, region)

        # (Re)build async tile loader bound to the current engine.
        if self._tile_loader is not None:
            self._tile_loader.stop()
        self._tile_loader = AsyncTileLoader(self._engine, parent=self)
        self._tile_loader.tiles_ready.connect(self._on_tiles_ready)
        self._last_applied_id = 0

        self._region = region
        self._channels = [ch.name for ch in acq.channels]
        self._active_channels = list(range(len(acq.channels)))
        self._channel_clims: dict[int, tuple[float, float]] = {}

        # Build per-channel toggle checkboxes
        self._build_channel_checkboxes()

        # Configure sliders
        self.channel_slider.setRange(0, max(0, len(acq.channels) - 1))
        nz = acq.z_stack.nz if acq.z_stack else 1
        self.z_slider.setRange(0, max(0, nz - 1))
        nt = acq.time_series.nt if acq.time_series else 1
        self.t_slider.setRange(0, max(0, nt - 1))

        # Composite mode: canvas renders RGB directly
        self._canvas.set_cmap("grays")
        self._canvas.set_clim((0.0, 1.0))

        # Fit camera to bounding box FIRST (so viewport is valid)
        bb = self._engine.bounding_box()
        self._canvas.set_range(*bb)

        # NOW compute per-channel contrast using the real viewport
        visible = self._engine._index.query(*bb) if self._engine._index else []
        fov_indices = [f.fov_index for f in visible] if visible else None
        for ch_idx in self._active_channels:
            p1, p99 = self._engine.compute_contrast(channel=ch_idx, fov_indices=fov_indices)
            self._channel_clims[ch_idx] = (p1, p99)

        # Initial render
        self._refresh()

    def _build_channel_checkboxes(self) -> None:
        """Create per-channel toggle checkboxes for composite control."""
        from PySide6.QtWidgets import QCheckBox

        from squid_tools.viewer.colormaps import get_channel_hex

        # Clear existing
        for cb in self._channel_checkboxes:
            self._channel_row.removeWidget(cb)
            cb.deleteLater()
        self._channel_checkboxes.clear()

        for _i, name in enumerate(self._channels):
            # Short label: extract wavelength or use name
            short = name
            for pattern in ("405", "488", "561", "638", "730"):
                if pattern in name:
                    short = f"{pattern}nm"
                    break

            color = get_channel_hex(name)
            cb = QCheckBox(short)
            cb.setChecked(True)
            cb.setToolTip(f"Toggle {name}")
            cb.setStyleSheet(f"QCheckBox {{ color: {color}; }}")
            cb.toggled.connect(self._on_channel_toggled)
            self._channel_row.addWidget(cb)
            self._channel_checkboxes.append(cb)

    def _on_channel_toggled(self) -> None:
        """Channel checkbox changed. Update active channels and refresh."""
        self._active_channels = [
            i for i, cb in enumerate(self._channel_checkboxes) if cb.isChecked()
        ]
        self._canvas.clear()
        self._engine._display_cache.clear()
        self._refresh()

    def set_pipeline(self, transforms: list) -> None:
        self._engine.set_pipeline(transforms)
        self._refresh()

    def set_borders_visible(self, visible: bool) -> None:
        self._canvas.set_borders_visible(visible)

    def _on_draw(self, event: object) -> None:
        """Canvas was drawn (after pan/zoom). Schedule a refresh."""
        self._refresh_timer.start()

    def _on_slider_changed(self) -> None:
        """Slider changed (z or t). Clear tiles and refresh composite."""
        # Clear all rendered tiles
        self._canvas.clear()

        # Recompute per-channel contrast using visible FOVs for efficiency
        viewport = self._canvas.get_viewport()
        visible = self._engine._index.query(*viewport) if self._engine._index else []
        fov_indices = [f.fov_index for f in visible] if visible else None
        for ch_idx in self._active_channels:
            p1, p99 = self._engine.compute_contrast(
                channel=ch_idx, z=self.z_slider.value(), timepoint=self.t_slider.value(),
                fov_indices=fov_indices,
            )
            self._channel_clims[ch_idx] = (p1, p99)

        # Clear display cache
        self._engine._display_cache.clear()

        # Load fresh composite tiles
        self._refresh()

    def _refresh(self) -> None:
        """Dispatch a tile request to the async loader. Non-blocking."""
        if not self._engine.is_loaded():
            return
        if self._tile_loader is None:
            return
        viewport = self._canvas.get_viewport()
        sw, sh = self._canvas.get_screen_size()
        if sw == 0 or sh == 0:
            return
        self._tile_loader.request(
            viewport=viewport,
            screen_width=sw,
            screen_height=sh,
            active_channels=self._active_channels,
            channel_names=self._channels,
            channel_clims=self._channel_clims,
            z=self.z_slider.value(),
            timepoint=self.t_slider.value(),
        )

    def _on_tiles_ready(self, request_id: int, tiles: object) -> None:
        """Apply tiles to canvas, dropping stale (superseded) replies."""
        if request_id < self._last_applied_id:
            return
        self._last_applied_id = request_id
        self._canvas.render_tiles(tiles)  # type: ignore[arg-type]

    def closeEvent(self, event: object) -> None:  # noqa: N802
        if self._tile_loader is not None:
            self._tile_loader.stop()
        super().closeEvent(event)  # type: ignore[arg-type]

    def _on_selection_drawn(
        self, rect: tuple[float, float, float, float],
    ) -> None:
        """Shift+drag released. Convert mm rectangle to FOV indices."""
        if not self._engine.is_loaded():
            return
        x_min, y_min, x_max, y_max = rect
        # Tiny rectangles = clear selection
        if abs(x_max - x_min) < 1e-6 or abs(y_max - y_min) < 1e-6:
            self.selection.clear()
            return
        visible = self._engine.visible_fov_indices(x_min, y_min, x_max, y_max)
        self.selection.set_selection(visible)

    def _on_selection_changed(self, selected: set) -> None:
        """Selection changed. Update canvas border colors."""
        self._canvas.set_selected_ids(selected)

    def contextMenuEvent(self, event: object) -> None:  # type: ignore[override]  # noqa: N802
        menu = QMenu(self)
        fit_action = QAction("Fit View", self)
        fit_action.triggered.connect(lambda: (
            self._canvas.set_range(*self._engine.bounding_box()),
            self._refresh(),
        ))
        menu.addAction(fit_action)
        toggle_borders = QAction("Toggle Borders", self)
        toggle_borders.triggered.connect(
            lambda: self._canvas.set_borders_visible(not self._canvas._borders_visible)
        )
        menu.addAction(toggle_borders)
        menu.exec(event.globalPos())  # type: ignore[union-attr]
