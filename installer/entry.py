# installer/entry.py
"""Entry point for PyInstaller frozen executable."""
from __future__ import annotations

import os
import sys


def _setup_frozen_env() -> None:
    """Configure paths for frozen PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle
        bundle_dir = os.path.dirname(sys.executable)
        # Set Qt plugin path
        qt_plugin_path = os.path.join(bundle_dir, "PyQt5", "Qt5", "plugins")
        if os.path.isdir(qt_plugin_path):
            os.environ["QT_PLUGIN_PATH"] = qt_plugin_path


def main() -> None:
    _setup_frozen_env()
    from squid_tools.gui.app import main as gui_main

    gui_main()


if __name__ == "__main__":
    main()
