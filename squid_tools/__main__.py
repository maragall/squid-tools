"""CLI entry point: python -m squid_tools."""

from __future__ import annotations

import argparse
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="squid-tools",
        description="Squid-Tools: Post-processing connector for Cephla-Lab/Squid",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"squid-tools {_get_version()}",
    )
    parser.add_argument(
        "--dev",
        nargs="?",
        const=True,
        default=None,
        metavar="PLUGIN_FILE",
        help="Launch in dev mode, optionally hot-loading a plugin file",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to a Squid acquisition directory to open",
    )

    args = parser.parse_args()

    from squid_tools.logger import setup_logging  # noqa: PLC0415

    log_dir = setup_logging()
    logging.getLogger("squid_tools").info("Logging to %s", log_dir)

    import os  # noqa: PLC0415
    os.environ.setdefault("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", ""))

    from pathlib import Path  # noqa: PLC0415

    from PySide6.QtWidgets import QApplication  # noqa: PLC0415

    from squid_tools.gui.app import MainWindow  # noqa: PLC0415

    app = QApplication(sys.argv)
    from squid_tools.gui.style import apply_style  # noqa: PLC0415
    apply_style(app)
    window = MainWindow()

    if args.path:
        window.open_acquisition(Path(args.path))

    if args.dev and args.dev is not True:
        from squid_tools.gui.dev_panel import DevConsole, load_plugin_from_file  # noqa: PLC0415
        plugin_path = Path(args.dev)
        if plugin_path.exists():
            plugins = load_plugin_from_file(plugin_path)
            for p in plugins:
                window.controller.registry.register(p)
            dev_console = DevConsole()
            for p in plugins:
                dev_console.log(f"Loaded: {p.name} ({p.category})")
                warnings = (
                    p.validate(window.controller.acquisition)
                    if window.controller.acquisition
                    else []
                )
                for w in warnings:
                    dev_console.log(f"  Warning: {w}")
                dev_console.run_test_cases(p)
            dev_console.show()

    window.show()
    sys.exit(app.exec())


def _get_version() -> str:
    from squid_tools import __version__  # noqa: PLC0415

    return __version__


if __name__ == "__main__":
    main()
