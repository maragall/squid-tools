"""Centers its single child widget at the largest square fitting its rect.

Pure geometry. No Qt layout, no sizePolicy puzzle — on resize:
    side = min(width, height)
    child rect = ((W - side) / 2, (H - side) / 2, side, side)
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


class SquareContainer(QWidget):
    """QWidget that keeps its one child square + centered."""

    def setCentralWidget(self, widget: QWidget) -> None:  # noqa: N802
        """Parent the widget to this container and re-layout."""
        widget.setParent(self)
        widget.show()
        self._relayout()

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        if event is not None:
            super().resizeEvent(event)  # type: ignore[arg-type]
        self._relayout()

    def _relayout(self) -> None:
        child = self._child()
        if child is None:
            return
        w, h = self.width(), self.height()
        side = max(0, min(w, h))
        x = (w - side) // 2
        y = (h - side) // 2
        child.setGeometry(x, y, side, side)

    def _child(self) -> QWidget | None:
        for c in self.children():
            if isinstance(c, QWidget):
                return c
        return None
