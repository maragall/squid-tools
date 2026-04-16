"""Dev mode: hot-load plugins from .py files.

Loads a Python file, finds ProcessingPlugin subclasses, instantiates
them, and returns them for registration. Also provides a console
widget for displaying validation and test results.
"""

from __future__ import annotations

import contextlib
import importlib.util
import inspect
import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from squid_tools.processing.base import ProcessingPlugin


def load_plugin_from_file(path: Path) -> list[ProcessingPlugin]:
    """Load a .py file and return all ProcessingPlugin subclasses found.

    Returns empty list on any error (syntax, import, no plugins found).
    """
    from squid_tools.processing.base import ProcessingPlugin as BaseClass

    try:
        spec = importlib.util.spec_from_file_location(
            f"dev_plugin_{path.stem}", str(path)
        )
        if spec is None or spec.loader is None:
            return []

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        plugins: list[ProcessingPlugin] = []
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseClass)
                and obj is not BaseClass
                and hasattr(obj, "name")
            ):
                with contextlib.suppress(Exception):
                    plugins.append(obj())

        return plugins

    except Exception:
        traceback.print_exc()
        return []


class DevConsole(QWidget):
    """Console panel for dev mode output."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(QLabel("Dev Console"))
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setStyleSheet(
            "background: #1a1a1a; color: #00ff00; font-family: monospace; font-size: 12px;"
        )
        layout.addWidget(self._output)

    def log(self, message: str) -> None:
        """Append a message to the console."""
        self._output.append(message)

    def clear(self) -> None:
        """Clear the console."""
        self._output.clear()

    def run_test_cases(self, plugin: ProcessingPlugin) -> None:
        """Run a plugin's test_cases() and display results."""
        import numpy as np

        cases = plugin.test_cases()
        self.log(f"\n--- Running test_cases for {plugin.name} ---")
        passed = 0
        for i, case in enumerate(cases):
            desc = case.get("description", f"case {i}")
            try:
                if "input" in case and "expected" in case:
                    result = plugin.process(case["input"], plugin.default_params())
                    if np.allclose(result, case["expected"]):
                        self.log(f"  PASS: {desc}")
                        passed += 1
                    else:
                        self.log(f"  FAIL: {desc} (output mismatch)")
                else:
                    self.log(f"  SKIP: {desc} (no input/expected)")
            except Exception as e:
                self.log(f"  ERROR: {desc} ({e})")
        self.log(f"  {passed}/{len(cases)} passed")
