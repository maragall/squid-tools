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
        self._updating_sliders: bool = False

        self.selection = SelectionState(self)
        self._canvas.selection_drawn.connect(self._on_selection_drawn)
        self.selection.selection_changed.connect(self._on_selection_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # The vispy canvas is wrapped in a SquareContainer so it stays 1:1
        # and centered. Sliders and nav rows live OUTSIDE that square.
        from squid_tools.viewer.square_container import SquareContainer

        native = self._canvas.native_widget()
        self._canvas_square = SquareContainer(self)
        if native is not None:
            self._canvas_square.setCentralWidget(native)  # type: ignore[arg-type]
        layout.addWidget(self._canvas_square, stretch=1)

        # Channel controls (one row per channel: checkbox + min/max sliders).
        # Built in load_acquisition when channels are known.
        from PySide6.QtWidgets import QCheckBox, QGridLayout, QPushButton
        self._channel_grid_container = QWidget(self)
        self._channel_grid = QGridLayout(self._channel_grid_container)
        self._channel_grid.setContentsMargins(8, 4, 8, 4)
        self._channel_grid.setHorizontalSpacing(8)
        self._channel_grid.setVerticalSpacing(2)
        self._channel_checkboxes: list[QCheckBox] = []
        self._channel_min_sliders: list[QSlider] = []
        self._channel_max_sliders: list[QSlider] = []
        self._channel_value_labels: list[QLabel] = []
        self._channel_reset_buttons: list[QPushButton] = []
        self._channel_data_ranges: list[tuple[float, float]] = []
        layout.addWidget(self._channel_grid_container)

        # Z / T / plane navigation (uniform, professional layout)
        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(8, 2, 8, 4)
        nav_row.setSpacing(8)

        z_label = QLabel("Z")
        z_label.setFixedWidth(16)
        nav_row.addWidget(z_label)
        self.z_slider = QSlider(Qt.Orientation.Horizontal)
        self.z_slider.setRange(0, 0)
        self.z_slider.setToolTip("Z-level")
        self.z_slider.valueChanged.connect(self._on_slider_changed)
        nav_row.addWidget(self.z_slider, stretch=1)
        self._z_value_label = QLabel("0 / 0")
        self._z_value_label.setFixedWidth(48)
        nav_row.addWidget(self._z_value_label)

        t_label = QLabel("T")
        t_label.setFixedWidth(16)
        nav_row.addWidget(t_label)
        self.t_slider = QSlider(Qt.Orientation.Horizontal)
        self.t_slider.setRange(0, 0)
        self.t_slider.setToolTip("Timepoint")
        self.t_slider.valueChanged.connect(self._on_slider_changed)
        nav_row.addWidget(self.t_slider, stretch=1)
        self._t_value_label = QLabel("0 / 0")
        self._t_value_label.setFixedWidth(48)
        nav_row.addWidget(self._t_value_label)

        layout.addLayout(nav_row)

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

        # NOW compute per-channel contrast using the real viewport and
        # snap the min/max sliders to the auto-detected p1/p99 (every
        # channel, so re-enabling a toggled-off channel has clim ready).
        visible = self._engine._index.query(*bb) if self._engine._index else []
        fov_indices = [f.fov_index for f in visible] if visible else None
        for ch_idx in range(len(self._channels)):
            p1, p99 = self._engine.compute_contrast(
                channel=ch_idx, fov_indices=fov_indices,
            )
            self._apply_auto_contrast_to_channel(ch_idx, p1, p99)

        # Z/T labels
        self._update_nav_labels()

        # Initial render
        self._refresh()

    def _update_nav_labels(self) -> None:
        self._z_value_label.setText(
            f"{self.z_slider.value()} / {max(0, self.z_slider.maximum())}",
        )
        self._t_value_label.setText(
            f"{self.t_slider.value()} / {max(0, self.t_slider.maximum())}",
        )

    def _build_channel_checkboxes(self) -> None:
        """Create per-channel control rows (checkbox + min/max sliders + reset).

        Each channel gets:
          row: [☐ wavelength-nm] [min ═══════] [max ═══════] [value] [reset]
        Colored by channel hex. Sliders operate in 0..10000 ticks mapped to
        the channel's data range (read from engine.compute_contrast).
        """
        from PySide6.QtWidgets import QCheckBox, QPushButton

        from squid_tools.viewer.colormaps import get_channel_hex

        # Clear the existing grid completely.
        while self._channel_grid.count():
            item = self._channel_grid.takeAt(0)
            if item is None:
                break
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._channel_checkboxes.clear()
        self._channel_min_sliders.clear()
        self._channel_max_sliders.clear()
        self._channel_value_labels.clear()
        self._channel_reset_buttons.clear()
        self._channel_data_ranges.clear()

        # ONE slider per channel = the upper contrast limit. Lower stays at
        # the auto-detected p1 set by _apply_auto_contrast_to_channel().
        # Layout per row: [☐ wavelength] [contrast slider] [auto reset]
        # Min sliders are kept as hidden objects so the rest of the
        # contrast pipeline (which reads min+max ticks) keeps working.
        slider_height = 14
        for i, name in enumerate(self._channels):
            short = name
            for pattern in ("405", "488", "561", "638", "730"):
                if pattern in name:
                    short = f"{pattern}nm"
                    break

            color = get_channel_hex(name)
            cb = QCheckBox(short)
            cb.setChecked(True)
            cb.setFixedWidth(64)
            cb.setToolTip(f"Show/hide {name} in composite")
            cb.setStyleSheet(f"QCheckBox {{ color: {color}; font-weight: 500; }}")
            cb.toggled.connect(self._on_channel_toggled)
            self._channel_grid.addWidget(cb, i, 0)

            # Hidden min slider (not added to the grid). _on_contrast_changed
            # still reads its tick value as the lower clim.
            min_slider = QSlider(Qt.Orientation.Horizontal)
            min_slider.setRange(0, 10000)
            min_slider.setValue(0)
            min_slider.hide()

            max_slider = QSlider(Qt.Orientation.Horizontal)
            max_slider.setRange(0, 10000)
            max_slider.setValue(10000)
            max_slider.setFixedHeight(slider_height)
            max_slider.setToolTip(f"{name}: brightness / contrast")
            max_slider.valueChanged.connect(self._on_contrast_changed)
            self._channel_grid.addWidget(max_slider, i, 1)

            value_label = QLabel("")
            self._channel_grid.addWidget(value_label, i, 2)

            reset_btn = QPushButton("auto")
            reset_btn.setFixedWidth(40)
            reset_btn.setFixedHeight(slider_height + 4)
            reset_btn.setToolTip(f"Reset auto-contrast for {name}")
            reset_btn.clicked.connect(lambda _=False, idx=i: self._reset_channel_contrast(idx))
            self._channel_grid.addWidget(reset_btn, i, 3)

            self._channel_checkboxes.append(cb)
            self._channel_min_sliders.append(min_slider)
            self._channel_max_sliders.append(max_slider)
            self._channel_value_labels.append(value_label)
            self._channel_reset_buttons.append(reset_btn)
            self._channel_data_ranges.append((0.0, 65535.0))

    def _on_channel_toggled(self) -> None:
        """Channel checkbox changed. Update active channels and refresh."""
        self._active_channels = [
            i for i, cb in enumerate(self._channel_checkboxes) if cb.isChecked()
        ]
        self._canvas.clear()
        self._engine._display_cache.clear()
        self._refresh()

    def _on_contrast_changed(self) -> None:
        """One of the contrast sliders moved. Recompute clims + refresh."""
        if self._updating_sliders:
            return
        for i in range(len(self._channels)):
            lo_tick = self._channel_min_sliders[i].value()
            hi_tick = self._channel_max_sliders[i].value()
            if hi_tick <= lo_tick:
                hi_tick = min(10000, lo_tick + 1)
                self._channel_max_sliders[i].blockSignals(True)
                self._channel_max_sliders[i].setValue(hi_tick)
                self._channel_max_sliders[i].blockSignals(False)
            d_lo, d_hi = self._channel_data_ranges[i]
            span = max(d_hi - d_lo, 1e-6)
            clim_lo = d_lo + (lo_tick / 10000.0) * span
            clim_hi = d_lo + (hi_tick / 10000.0) * span
            self._channel_clims[i] = (clim_lo, clim_hi)
            self._channel_value_labels[i].setText(
                f"{clim_lo:.0f}..{clim_hi:.0f}",
            )
        self._engine._display_cache.clear()
        self._refresh()

    def _reset_channel_contrast(self, channel: int) -> None:
        """Recompute auto-contrast for one channel and snap sliders."""
        viewport = self._canvas.get_viewport()
        visible = self._engine._index.query(*viewport) if self._engine._index else []
        fov_indices = [f.fov_index for f in visible] if visible else None
        p1, p99 = self._engine.compute_contrast(
            channel=channel,
            z=self.z_slider.value(),
            timepoint=self.t_slider.value(),
            fov_indices=fov_indices,
        )
        self._apply_auto_contrast_to_channel(channel, p1, p99)
        self._engine._display_cache.clear()
        self._refresh()

    def _apply_auto_contrast_to_channel(
        self, channel: int, clim_lo: float, clim_hi: float,
    ) -> None:
        """Update one channel's data range + slider positions + clim."""
        data_lo = min(clim_lo, 0.0) if clim_lo < 0 else 0.0
        data_hi = max(clim_hi * 2.0, clim_hi + 1.0)
        self._channel_data_ranges[channel] = (data_lo, data_hi)
        span = max(data_hi - data_lo, 1e-6)
        lo_tick = int(max(0, min(10000, (clim_lo - data_lo) / span * 10000)))
        hi_tick = int(max(0, min(10000, (clim_hi - data_lo) / span * 10000)))
        self._updating_sliders = True
        self._channel_min_sliders[channel].setValue(lo_tick)
        self._channel_max_sliders[channel].setValue(hi_tick)
        self._updating_sliders = False
        self._channel_clims[channel] = (clim_lo, clim_hi)
        self._channel_value_labels[channel].setText(
            f"{clim_lo:.0f}..{clim_hi:.0f}",
        )

    def set_pipeline(self, transforms: list) -> None:
        self._engine.set_pipeline(transforms)
        self._refresh()

    def set_borders_visible(self, visible: bool) -> None:
        self._canvas.set_borders_visible(visible)

    def _on_draw(self, event: object) -> None:
        """Canvas was drawn (after pan/zoom). Schedule a refresh."""
        self._refresh_timer.start()

    def _on_slider_changed(self) -> None:
        """Z or T slider moved. Refresh composite. Preserve user clims."""
        self._update_nav_labels()
        self._canvas.clear()
        self._engine._display_cache.clear()
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
        menu.addSeparator()
        view_3d_action = QAction("Open 3D View…", self)
        view_3d_action.setToolTip(
            "Open a ray-marched 3D view of the current FOV's z-stack.",
        )
        view_3d_action.triggered.connect(self._open_3d_viewer)
        menu.addAction(view_3d_action)
        menu.addSeparator()
        export_fused = QAction("Export Stitched Region…", self)
        export_fused.setToolTip(
            "Run stitching fusion on the visible region and save as OME-TIFF.",
        )
        export_fused.triggered.connect(self._export_stitched)
        menu.addAction(export_fused)
        menu.exec(event.globalPos())  # type: ignore[union-attr]

    def _export_stitched(self) -> None:
        """Run stitcher fusion on the visible region and write an OME-TIFF.

        Ports the fusion step from the reference `_audit/stitcher` — live
        run_live only does registration + optimization; this is the missing
        seam-blended export.
        """
        import logging
        from pathlib import Path

        import tifffile
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        from squid_tools.processing.stitching.plugin import (
            StitcherParams,
            StitcherPlugin,
        )

        log = logging.getLogger("squid_tools.viewer.widget")
        if not self._engine.is_loaded():
            return

        plugin = StitcherPlugin()
        try:
            params = plugin.default_params(self._engine._acquisition.optical)
            assert isinstance(params, StitcherParams)
        except ValueError as e:
            QMessageBox.warning(self, "Stitcher", str(e))
            return

        viewport = self._canvas.get_viewport()
        visible = self._engine.visible_fov_indices(*viewport)
        if len(visible) < 2:
            QMessageBox.information(
                self, "Export Stitched",
                "Zoom to cover at least 2 FOVs first.",
            )
            return

        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save stitched OME-TIFF",
            str(self._engine._acquisition.path / "stitched.ome.tiff"),
            "OME-TIFF (*.ome.tiff *.ome.tif);;All files (*)",
        )
        if not out_path:
            return

        log.info("Fusing %d visible FOVs to %s…", len(visible), out_path)
        try:
            fused = plugin.fuse_region_to_array(
                self._engine, params,
                channel=0, z=self.z_slider.value(),
                timepoint=self.t_slider.value(),
                fov_indices=visible,
            )
        except Exception as e:
            log.exception("fusion failed")
            QMessageBox.warning(self, "Stitcher", f"Fusion failed: {e}")
            return

        tifffile.imwrite(out_path, fused, photometric="minisblack")
        log.info("Stitched output written: %s (%s)", out_path, fused.shape)
        QMessageBox.information(
            self, "Export Stitched",
            f"Saved {Path(out_path).name}\nShape: {fused.shape}",
        )

    def _open_3d_viewer(self) -> None:
        """Launch a separate 3D viewer window bound to the current engine."""
        if not self._engine.is_loaded():
            return
        from squid_tools.viewer.widget_3d import Viewer3DWidget

        viewer = Viewer3DWidget(
            engine=self._engine,
            channel_names=self._channels,
        )
        viewer.show()
        # Keep a reference so it isn't GC'd immediately.
        self._viewer_3d = viewer
