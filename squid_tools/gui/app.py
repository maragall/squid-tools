"""Main window for the Squid-Tools GUI application."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtSvg import QSvgWidget
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from squid_tools.core.readers import open_acquisition
from squid_tools.core.registry import discover_plugins
from squid_tools.gui.controls import ControlsPanel
from squid_tools.gui.log_panel import LogPanel
from squid_tools.gui.processing_tabs import ProcessingTabs
from squid_tools.gui.theme import STYLESHEET
from squid_tools.gui.wellplate import RegionSelector

_LOGO_PATH = Path(__file__).parent / "cephla_logo.svg"


class MainWindow(QMainWindow):
    """Main application window.

    Layout
    ------
    QVBoxLayout (central widget)
    ├── ProcessingTabs          (top, max height 200 px)
    ├── QHBoxLayout (stretch=1)
    │   ├── ControlsPanel       (left,  fixed 160 px)
    │   ├── QLabel placeholder  (center, stretch=1)
    │   └── RegionSelector      (right, fixed 200 px)
    └── LogPanel                (bottom)
    """

    _MIN_WIDTH = 1200
    _MIN_HEIGHT = 800

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Squid-Tools")
        self.setMinimumSize(self._MIN_WIDTH, self._MIN_HEIGHT)
        if _LOGO_PATH.exists():
            self.setWindowIcon(QIcon(str(_LOGO_PATH)))

        # ---- Central widget & root layout ----
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(4)

        # ---- Header with logo ----
        header = QHBoxLayout()
        header.setSpacing(8)
        if _LOGO_PATH.exists():
            logo = QSvgWidget(str(_LOGO_PATH))
            logo.setFixedSize(32, 32)
            header.addWidget(logo)
        title_label = QLabel("Squid-Tools")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #ffffff;")
        header.addWidget(title_label)
        header.addStretch()
        root_layout.addLayout(header)

        # ---- Processing tabs (top) ----
        self._processing_tabs = ProcessingTabs()
        root_layout.addWidget(self._processing_tabs)

        # ---- Middle row ----
        middle = QHBoxLayout()
        middle.setSpacing(4)

        self._controls = ControlsPanel()
        middle.addWidget(self._controls)

        self._viewer_placeholder = QLabel("Open an acquisition to begin")
        self._viewer_placeholder.setToolTip(
            "Image viewer: open an acquisition via File > Open Acquisition"
        )
        self._viewer_placeholder.setStyleSheet(
            "QLabel { background-color: #1e1e1e; color: #666;"
            "border: 1px solid #555; font-size: 14pt; }"
        )
        self._viewer_placeholder.setAlignment(Qt.AlignCenter)
        middle.addWidget(self._viewer_placeholder, stretch=1)

        self._region_selector = RegionSelector()
        middle.addWidget(self._region_selector)

        root_layout.addLayout(middle, stretch=1)

        # ---- Log panel (bottom) ----
        self._log_panel = LogPanel()
        root_layout.addWidget(self._log_panel)

        # ---- Menu bar ----
        self._build_menu()

        # ---- Load plugins ----
        self._load_plugins()

        # ---- Connect signals ----
        self._controls.view_mode_changed.connect(self._on_view_mode_changed)
        self._controls.borders_toggled.connect(self._on_borders_toggled)
        self._region_selector.region_selected.connect(self._on_region_selected)
        self._processing_tabs.run_requested.connect(self._on_run_requested)

        self._log_panel.set_status("Ready")

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")

        open_action = QAction("&Open Acquisition", self)
        open_action.setShortcut("Ctrl+O")
        open_action.setToolTip("Open a Squid acquisition directory")
        open_action.triggered.connect(self._on_open_acquisition)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.setToolTip("Exit the application")
        quit_action.triggered.connect(QApplication.instance().quit)
        file_menu.addAction(quit_action)

    # ------------------------------------------------------------------
    # Plugin loading
    # ------------------------------------------------------------------

    def _load_plugins(self) -> None:
        plugins = discover_plugins()
        for plugin in plugins.values():
            self._processing_tabs.add_plugin(plugin)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_open_acquisition(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Open Acquisition Directory",
            "",
        )
        if not path:
            return

        self._log_panel.set_status(f"Opening acquisition: {path} …")
        try:
            acq = open_acquisition(path)
            self._region_selector.set_acquisition(acq)
            self._log_panel.set_status(
                f"Loaded acquisition: {path}  ({len(acq.regions)} region(s))"
            )
        except Exception as exc:  # noqa: BLE001
            self._log_panel.set_status(f"Error opening acquisition: {exc}")

    def _on_view_mode_changed(self, mode: str) -> None:
        self._log_panel.set_status(f"View mode: {mode}")

    def _on_borders_toggled(self, enabled: bool) -> None:
        state = "on" if enabled else "off"
        self._log_panel.set_status(f"FOV borders: {state}")

    def _on_region_selected(self, region_id: str) -> None:
        self._log_panel.set_status(f"Selected region: {region_id}")

    def _on_run_requested(self, plugin_name: str, params: object) -> None:
        self._log_panel.set_status(f"Running plugin '{plugin_name}' …")


def main() -> None:
    """Entry point for the Squid-Tools GUI."""
    app = QApplication(sys.argv)
    app.setApplicationName("Squid-Tools")
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
