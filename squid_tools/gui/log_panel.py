"""Log panel widget for the Squid-Tools GUI.

Displays status messages, GPU info, and memory usage in a horizontal bar.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget


def _detect_gpu() -> str:
    try:
        import cupy as cp  # type: ignore[import-untyped]

        device = cp.cuda.Device(0)
        name = cp.cuda.runtime.getDeviceProperties(device.id)["name"].decode()
        return f"GPU: {name}"
    except Exception:
        return "GPU: not detected (CPU mode)"


class LogPanel(QWidget):
    """Horizontal status bar: status label | stretch | GPU label | memory label."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        self._status_label = QLabel("Ready")
        self._status_label.setToolTip("Current operation status")
        layout.addWidget(self._status_label)

        layout.addStretch(1)

        self._gpu_label = QLabel(_detect_gpu())
        self._gpu_label.setToolTip(
            "GPU device used for processing. Shows 'CPU mode' when no CUDA GPU is available."
        )
        layout.addWidget(self._gpu_label)

        self._memory_label = QLabel("Mem: –")
        self._memory_label.setToolTip("GPU/CPU memory usage: used / total (MB)")
        layout.addWidget(self._memory_label)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_status(self, msg: str) -> None:
        """Update the status message on the left side of the panel."""
        self._status_label.setText(msg)

    def set_memory(self, used_mb: float, total_mb: float) -> None:
        """Update the memory usage display."""
        self._memory_label.setText(f"Mem: {used_mb:.0f} / {total_mb:.0f} MB")
