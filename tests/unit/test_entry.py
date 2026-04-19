"""Tests for CLI entry point."""

import os
import subprocess
import sys


class TestCLIEntry:
    def test_module_entry_help(self) -> None:
        """python -m squid_tools --help should exit 0."""
        result = subprocess.run(
            [sys.executable, "-m", "squid_tools", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        )
        assert result.returncode == 0
        assert "squid-tools" in result.stdout.lower() or "usage" in result.stdout.lower()

    def test_module_entry_version(self) -> None:
        """python -m squid_tools --version should print version."""
        result = subprocess.run(
            [sys.executable, "-m", "squid_tools", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        )
        assert result.returncode == 0
        assert "0.1.0" in result.stdout


class TestLoggerWiring:
    def test_main_calls_setup_logging_before_qapplication(self, monkeypatch, tmp_path) -> None:
        import sys

        import squid_tools.__main__ as main_mod

        calls: list[str] = []

        def fake_setup(log_dir=None):
            calls.append("setup_logging")
            return tmp_path

        class FakeApp:
            def __init__(self, *a, **kw):
                calls.append("QApplication")
            def exec(self):
                return 0
            @staticmethod
            def instance():
                return None

        class FakeWindow:
            def __init__(self, *a, **kw):
                calls.append("MainWindow")
            def show(self):
                pass
            def open_acquisition(self, *a, **kw):
                pass
            controller = type("C", (), {"registry": type("R", (), {"register": staticmethod(lambda p: None)})(), "acquisition": None})()

        monkeypatch.setattr("squid_tools.logger.setup_logging", fake_setup)
        monkeypatch.setattr("PySide6.QtWidgets.QApplication", FakeApp)
        monkeypatch.setattr("squid_tools.gui.app.MainWindow", FakeWindow)
        monkeypatch.setattr("squid_tools.gui.style.apply_style", lambda app: None)
        monkeypatch.setattr(sys, "argv", ["squid-tools"])
        monkeypatch.setattr(sys, "exit", lambda *a, **kw: None)

        main_mod.main()

        assert calls.index("setup_logging") < calls.index("QApplication")
