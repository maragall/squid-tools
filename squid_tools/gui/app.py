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
from squid_tools.gui.viewer import ViewerWidget
from squid_tools.gui.wellplate import RegionSelector

_LOGO_PATH = Path(__file__).parent / "cephla_logo.svg"


class MainWindow(QMainWindow):

    _MIN_WIDTH = 1200
    _MIN_HEIGHT = 800

    def __init__(self, open_path: str | None = None) -> None:
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

        # ndviewer_light viewer (the core)
        self._viewer = ViewerWidget()
        middle.addWidget(self._viewer.widget, stretch=1)

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

        # Signals
        self._controls.view_mode_changed.connect(self._on_mode)
        self._controls.borders_toggled.connect(self._on_borders)
        self._region_selector.region_selected.connect(self._on_region)
        self._tabs.run_requested.connect(self._on_run)

        self._log.set_status("Ready")

        # Auto-open if path provided
        if open_path:
            self._open_path(open_path)

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

    def _open_path(self, path: str) -> None:
        self._log.set_status(f"Opening: {path}")
        try:
            acq = open_acquisition(Path(path))
            self._region_selector.set_acquisition(acq)
            self._viewer.load_acquisition(acq)
            self._log.set_status(f"Loaded: {Path(path).name} ({len(acq.regions)} region(s))")
        except Exception as exc:  # noqa: BLE001
            self._log.set_status(f"Error: {exc}")

    def _on_open(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open Acquisition Directory")
        if path:
            self._open_path(path)

    def _on_mode(self, mode: str) -> None:
        self._log.set_status(f"View: {mode}")

    def _on_borders(self, on: bool) -> None:
        pass  # TODO: wire to mosaic overlay

    def _on_region(self, region_id: str) -> None:
        self._log.set_status(f"Region: {region_id}")

    def _on_run(self, name: str, params: object) -> None:
        self._log.set_status(f"Running {name}...")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Squid-Tools")
    app.setStyleSheet(STYLESHEET)

    # Accept optional path argument
    open_path = sys.argv[1] if len(sys.argv) > 1 else None
    window = MainWindow(open_path=open_path)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
