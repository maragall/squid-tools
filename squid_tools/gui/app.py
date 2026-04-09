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
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from squid_tools.core.data_model import Acquisition
from squid_tools.core.readers import open_acquisition
from squid_tools.core.registry import discover_plugins
from squid_tools.gui.controls import ControlsPanel
from squid_tools.gui.log_panel import LogPanel
from squid_tools.gui.processing_tabs import ProcessingTabs
from squid_tools.gui.theme import STYLESHEET
from squid_tools.gui.viewer import UnifiedViewer
from squid_tools.gui.wellplate import RegionSelector

_LOGO_PATH = Path(__file__).parent / "cephla_logo.svg"


class MainWindow(QMainWindow):

    _MIN_WIDTH = 1200
    _MIN_HEIGHT = 800

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Squid-Tools")
        self.setMinimumSize(self._MIN_WIDTH, self._MIN_HEIGHT)
        if _LOGO_PATH.exists():
            self.setWindowIcon(QIcon(str(_LOGO_PATH)))

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Header
        header = QHBoxLayout()
        header.setSpacing(8)
        if _LOGO_PATH.exists():
            logo = QSvgWidget(str(_LOGO_PATH))
            logo.setFixedSize(32, 32)
            header.addWidget(logo)
        title = QLabel("Squid-Tools")
        title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #ffffff;")
        header.addWidget(title)
        header.addStretch()
        root.addLayout(header)

        # Processing tabs (top)
        self._tabs = ProcessingTabs()
        root.addWidget(self._tabs)

        # Middle: controls | viewer | region selector
        middle = QHBoxLayout()
        middle.setSpacing(4)

        self._controls = ControlsPanel()
        middle.addWidget(self._controls)

        # Viewer: placeholder until acquisition loaded, then unified viewer
        self._stack = QStackedWidget()
        self._placeholder = QLabel("Open an acquisition to begin")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet(
            "QLabel { background-color: #1e1e1e; color: #666;"
            "border: 1px solid #555; font-size: 14pt; }"
        )
        self._stack.addWidget(self._placeholder)  # index 0

        self._viewer: UnifiedViewer | None = None
        middle.addWidget(self._stack, stretch=1)

        self._region_selector = RegionSelector()
        middle.addWidget(self._region_selector)

        root.addLayout(middle, stretch=1)

        # Log (bottom)
        self._log = LogPanel()
        root.addWidget(self._log)

        # Menu
        self._build_menu()

        # Plugins
        plugins = discover_plugins()
        for p in plugins.values():
            self._tabs.add_plugin(p)

        # State
        self._acq: Acquisition | None = None

        # Signals
        self._controls.view_mode_changed.connect(self._on_mode)
        self._controls.borders_toggled.connect(self._on_borders)
        self._region_selector.region_selected.connect(self._on_region)
        self._tabs.run_requested.connect(self._on_run)

        self._log.set_status("Ready")

    def _build_menu(self) -> None:
        menu = self.menuBar()
        f = menu.addMenu("&File")

        o = QAction("&Open Acquisition", self)
        o.setShortcut("Ctrl+O")
        o.setToolTip("Open a Squid acquisition directory")
        o.triggered.connect(self._on_open)
        f.addAction(o)

        f.addSeparator()

        q = QAction("&Quit", self)
        q.setShortcut("Ctrl+Q")
        q.triggered.connect(QApplication.instance().quit)
        f.addAction(q)

    def _ensure_viewer(self) -> UnifiedViewer:
        if self._viewer is None:
            self._viewer = UnifiedViewer()
            self._stack.addWidget(self._viewer.widget)  # index 1
        self._stack.setCurrentIndex(1)
        return self._viewer

    def _on_open(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open Acquisition Directory")
        if not path:
            return
        self._log.set_status(f"Opening: {path}")
        try:
            acq = open_acquisition(path)
            self._acq = acq
            self._region_selector.set_acquisition(acq)
            v = self._ensure_viewer()
            first = next(iter(acq.regions))
            v.set_acquisition(acq, first)
            self._log.set_status(f"Loaded: {Path(path).name} ({len(acq.regions)} region(s))")
        except Exception as exc:  # noqa: BLE001
            self._log.set_status(f"Error: {exc}")

    def _on_mode(self, mode: str) -> None:
        if self._viewer:
            self._viewer.set_mode(mode)
        self._log.set_status(f"View: {mode}")

    def _on_borders(self, on: bool) -> None:
        if self._viewer:
            self._viewer.show_borders(on)

    def _on_region(self, region_id: str) -> None:
        if self._acq and self._viewer:
            self._viewer.set_acquisition(self._acq, region_id)
            self._log.set_status(f"Region: {region_id}")

    def _on_run(self, name: str, params: object) -> None:
        self._log.set_status(f"Running {name}...")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Squid-Tools")
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
