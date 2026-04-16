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
