"""Selection state for FOV selection in the viewer.

Thread-safe via Qt signals. The set of selected FOV indices is
the single source of truth. Widgets subscribe to selection_changed.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class SelectionState(QObject):
    """Tracks currently selected FOV indices."""

    selection_changed = Signal(set)  # set[int] of FOV indices

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._selected: set[int] = set()

    @property
    def selected(self) -> set[int]:
        """Return a copy of the currently selected indices."""
        return self._selected.copy()

    def set_selection(self, indices: set[int]) -> None:
        """Replace the current selection. Emit if changed."""
        new = set(indices)
        if new == self._selected:
            return
        self._selected = new
        self.selection_changed.emit(self.selected)

    def clear(self) -> None:
        """Clear the selection. Emit if it was non-empty."""
        if not self._selected:
            return
        self._selected = set()
        self.selection_changed.emit(self.selected)

    def is_empty(self) -> bool:
        return len(self._selected) == 0
