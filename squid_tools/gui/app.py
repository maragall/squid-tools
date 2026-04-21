"""Main application window for Squid-Tools.

Composes all GUI panels: controls (left), viewer (center),
region selector (right), processing tabs (top), log panel (bottom).
Wired to AppController for data loading and processing.

One continuous viewer. No mode switching.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from squid_tools.core.registry import PluginRegistry
from squid_tools.gui.algorithm_runner import AlgorithmRunner
from squid_tools.gui.controller import AppController
from squid_tools.gui.controls import ControlsPanel
from squid_tools.gui.log_panel import LogPanel
from squid_tools.gui.processing_tabs import ProcessingTabs
from squid_tools.gui.region_selector import RegionSelector


class MainWindow(QMainWindow):
    """Squid-Tools main window."""

    def __init__(self, registry: PluginRegistry | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Squid-Tools")
        self.setMinimumSize(1024, 768)

        self.controller = AppController(registry)

        # Register default plugins before creating ProcessingTabs
        self._register_default_plugins()

        # Menu bar
        self._setup_menus()

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Top: processing tabs (after plugin registration so tabs see the plugins)
        self.processing_tabs = ProcessingTabs(self.controller.registry)
        self.processing_tabs.toggle_changed.connect(self._on_toggle_changed)
        main_layout.addWidget(self.processing_tabs)

        # Middle: controls | viewer | region selector
        middle_splitter = QSplitter(Qt.Horizontal)

        self.controls_panel = ControlsPanel()
        self.controls_panel.setMaximumWidth(150)
        self.controls_panel.borders_toggled.connect(self._on_borders_toggled)
        middle_splitter.addWidget(self.controls_panel)

        # Viewer placeholder (replaced when acquisition is opened)
        self._viewer_container = QWidget()
        self._viewer_layout = QVBoxLayout(self._viewer_container)
        self._viewer_layout.setContentsMargins(0, 0, 0, 0)
        middle_splitter.addWidget(self._viewer_container)

        self.region_selector = RegionSelector()
        self.region_selector.setMaximumWidth(200)
        self.region_selector.region_selected.connect(self._on_region_selected)
        middle_splitter.addWidget(self.region_selector)

        middle_splitter.setStretchFactor(0, 0)
        middle_splitter.setStretchFactor(1, 1)
        middle_splitter.setStretchFactor(2, 0)

        main_layout.addWidget(middle_splitter, stretch=1)

        # Bottom: log panel
        self.log_panel = LogPanel()
        self.log_panel.setMaximumHeight(150)
        self.log_panel.set_data_manager(self.controller.data_manager)
        main_layout.addWidget(self.log_panel)

        # Algorithm runner (background thread)
        self._algorithm_runner = AlgorithmRunner(self)
        self._algorithm_runner.progress_updated.connect(self._on_run_progress)
        self._algorithm_runner.run_complete.connect(self._on_run_complete)
        self._algorithm_runner.run_failed.connect(self._on_run_failed)

        # Connect run_requested signal from processing tabs
        self.processing_tabs.run_requested.connect(self._on_run_requested_tab)

        # Lazily created continuous viewer
        self._viewer = None

    def _register_default_plugins(self) -> None:
        """Register built-in processing plugins."""
        try:
            from squid_tools.processing.flatfield.plugin import FlatfieldPlugin
            self.controller.registry.register(FlatfieldPlugin())
        except ImportError:
            pass
        try:
            from squid_tools.processing.stitching.plugin import StitcherPlugin
            self.controller.registry.register(StitcherPlugin())
        except ImportError:
            pass
        try:
            from squid_tools.processing.decon.plugin import DeconvolutionPlugin
            self.controller.registry.register(DeconvolutionPlugin())
        except ImportError:
            pass

    def _setup_menus(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")

        open_action = QAction("&Open Acquisition...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.setToolTip("Open a Squid acquisition directory")
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _on_open(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open Acquisition Directory")
        if path:
            self.open_acquisition(Path(path))

    def open_acquisition(self, path: Path) -> None:
        """Load an acquisition and populate all panels."""
        try:
            self.log_panel.log(f"Loading: {path}")
            acq = self.controller.load_acquisition(path)
            self.log_panel.log(
                f"Format: {acq.format.value} | "
                f"Objective: {acq.objective.name} ({acq.objective.pixel_size_um} um/px) | "
                f"Regions: {len(acq.regions)} | "
                f"FOVs: {sum(len(r.fovs) for r in acq.regions.values())} | "
                f"Channels: {len(acq.channels)} ({', '.join(ch.name for ch in acq.channels)})"
            )
            if acq.z_stack:
                dz = acq.z_stack.delta_z_mm * 1000
                self.log_panel.log(f"Z-stack: {acq.z_stack.nz} planes, {dz:.1f} um step")
            if acq.time_series:
                nt = acq.time_series.nt
                dt = acq.time_series.delta_t_s
                self.log_panel.log(f"Time series: {nt} timepoints, {dt}s interval")

            self.region_selector.load_acquisition(acq)
            self.log_panel.set_status(f"Loaded: {path.name}")

            # Create viewer if needed
            if self._viewer is None:
                self._create_viewer()

            # Auto-select first region
            if acq.regions:
                first_region = next(iter(acq.regions))
                self.region_selector.set_selected_region(first_region)
                self.log_panel.log(f"Auto-selected region: {first_region}")
                self._viewer.load_acquisition(path, first_region)

        except Exception as e:
            import traceback
            self.log_panel.log(f"ERROR loading: {e}")
            self.log_panel.log(traceback.format_exc())

    def _create_viewer(self) -> None:
        """Lazily create the continuous viewer widget."""
        try:
            from squid_tools.viewer.widget import ViewerWidget
            self._viewer = ViewerWidget()
            self._viewer_layout.addWidget(self._viewer)
        except Exception as e:
            self.log_panel.log(f"Viewer init failed: {e}")

    def _on_region_selected(self, region_id: str) -> None:
        """Handle region selection: load stage view for the new region."""
        if self.controller.acquisition is None:
            return
        if self._viewer is None:
            return

        try:
            self.log_panel.log(f"Region selected: {region_id}")
            self._viewer.load_acquisition(self.controller.acquisition.path, region_id)
        except Exception as e:
            import traceback
            self.log_panel.log(f"ERROR region select: {e}")
            self.log_panel.log(traceback.format_exc())

    def _on_borders_toggled(self, visible: bool) -> None:
        """Toggle FOV borders on stage view."""
        if self._viewer is not None:
            self._viewer.set_borders_visible(visible)

    def _on_toggle_changed(self, plugin_name: str, active: bool) -> None:
        """Handle processing toggle: rebuild pipeline, refresh view."""
        self._rebuild_pipeline()

    def _rebuild_pipeline(self) -> None:
        """Build pipeline from active toggles and push to viewer."""
        transforms = []
        stitcher_active = False

        for name in self.processing_tabs.active_plugin_names():
            plugin = self.controller.registry.get(name)
            if plugin is None:
                continue

            if name == "Stitcher":
                stitcher_active = True
                continue  # Don't add stitcher to per-tile pipeline

            params_dict = self.processing_tabs.get_params(name)
            params_cls = plugin.parameters()
            params = (
                params_cls(**params_dict)
                if params_dict
                else plugin.default_params(
                    self.controller.acquisition.optical if self.controller.acquisition else None
                )
            )
            transforms.append(lambda frame, p=plugin, pr=params: p.process(frame, pr))

        self.controller.data_manager.set_pipeline(transforms)
        self.controller.data_manager.invalidate_thumbnails()

        if self._viewer is not None:
            self._viewer.set_pipeline(transforms)

        # Stitcher runs registration via its own plugin.run_live path, not
        # via the narrower engine.register_visible_tiles (which used different
        # pair-finding logic and reported "no pairs" on real acquisitions).
        # Toggling Stitcher off clears any previous overrides.
        if self._viewer is not None and self.controller.acquisition is not None:
            if stitcher_active:
                self._auto_run_stitcher()
            else:
                self._viewer._engine.clear_position_overrides()
                self._viewer._refresh()

    def _on_run_requested_tab(self, plugin_name: str, params_dict: dict) -> None:
        """Run a plugin on the current selection."""
        if self.controller.acquisition is None:
            self.log_panel.log(f"[{plugin_name}] No acquisition loaded.")
            self.processing_tabs.set_status(plugin_name, "No acquisition")
            return
        if self._viewer is None:
            self.log_panel.log(f"[{plugin_name}] Viewer not ready.")
            return
        plugin = self.controller.registry.get(plugin_name)
        if plugin is None:
            self.log_panel.log(f"[{plugin_name}] Plugin not registered.")
            return

        selection = self.viewer_selection() or None  # None means all
        params_cls = plugin.parameters()
        params = (
            params_cls(**params_dict)
            if params_dict
            else plugin.default_params(
                self.controller.acquisition.optical
                if self.controller.acquisition
                else None
            )
        )
        ok = self._algorithm_runner.run(
            plugin=plugin,
            selection=selection,
            engine=self._viewer._engine,
            params=params,
        )
        if not ok:
            self.log_panel.log(f"[{plugin_name}] Wait for current run to finish.")
            self.processing_tabs.set_status(plugin_name, "Waiting: another run in progress")
        else:
            sel_text = f"{len(selection)} tiles" if selection else "all FOVs"
            self.log_panel.log(f"[{plugin_name}] Run started on {sel_text}.")
            self.processing_tabs.set_status(plugin_name, "Running...")

    def viewer_selection(self) -> set[int]:
        """Return the current selection (empty set if no viewer)."""
        if self._viewer is None:
            return set()
        return self._viewer.selection.selected

    def _on_run_progress(
        self, plugin_name: str, phase: str, current: int, total: int,
    ) -> None:
        self.processing_tabs.set_status(
            plugin_name, f"{phase}: {current}/{total}",
        )

    def _on_run_complete(self, plugin_name: str, tiles_processed: int) -> None:
        self.processing_tabs.mark_calibrated(plugin_name)
        self.processing_tabs.set_status(
            plugin_name, f"Applied to {tiles_processed} tiles",
        )
        self.log_panel.log(f"[{plugin_name}] Complete.")
        # Refresh viewer so position overrides / pipeline changes show
        if self._viewer is not None:
            self._viewer._canvas.clear()
            self._viewer._refresh()

    def _on_run_failed(self, plugin_name: str, error_message: str) -> None:
        self.processing_tabs.set_status(plugin_name, f"Failed: {error_message[:80]}")
        self.log_panel.log(f"[{plugin_name}] FAILED: {error_message}")

    def _auto_run_stitcher(self) -> None:
        """Auto-run the Stitcher plugin when its toggle is first enabled.

        Uses the same AlgorithmRunner path as the Run button, so pair-finding
        and tile shifts are identical across manual and auto invocations.
        """
        if self._viewer is None or self.controller.acquisition is None:
            return
        plugin = self.controller.registry.get("Stitcher")
        if plugin is None:
            return
        params_dict = self.processing_tabs.get_params("Stitcher")
        params_cls = plugin.parameters()
        params = (
            params_cls(**params_dict)
            if params_dict
            else plugin.default_params(self.controller.acquisition.optical)
        )
        selection = self.viewer_selection() or None
        ok = self._algorithm_runner.run(
            plugin=plugin,
            selection=selection,
            engine=self._viewer._engine,
            params=params,
        )
        if ok:
            self.log_panel.log("[Stitcher] Auto-running after toggle...")
            self.processing_tabs.set_status("Stitcher", "Running...")


def main() -> None:
    """Launch Squid-Tools standalone."""
    app = QApplication(sys.argv)
    from squid_tools.gui.style import apply_style
    apply_style(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
