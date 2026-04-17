"""Tests for SelectionState."""

from pytestqt.qtbot import QtBot

from squid_tools.viewer.selection import SelectionState


class TestSelectionState:
    def test_starts_empty(self, qtbot: QtBot) -> None:
        state = SelectionState()
        assert state.is_empty()
        assert state.selected == set()

    def test_set_selection(self, qtbot: QtBot) -> None:
        state = SelectionState()
        state.set_selection({0, 1, 2})
        assert state.selected == {0, 1, 2}
        assert not state.is_empty()

    def test_selected_returns_copy(self, qtbot: QtBot) -> None:
        state = SelectionState()
        state.set_selection({0, 1, 2})
        s = state.selected
        s.add(99)
        assert state.selected == {0, 1, 2}

    def test_set_selection_emits_signal(self, qtbot: QtBot) -> None:
        state = SelectionState()
        with qtbot.waitSignal(state.selection_changed, timeout=500) as blocker:
            state.set_selection({5, 7})
        assert blocker.args[0] == {5, 7}

    def test_same_selection_no_emit(self, qtbot: QtBot) -> None:
        state = SelectionState()
        state.set_selection({0, 1})
        # Second call with identical set should NOT emit
        received = []
        state.selection_changed.connect(lambda s: received.append(s))
        state.set_selection({0, 1})
        assert received == []

    def test_clear(self, qtbot: QtBot) -> None:
        state = SelectionState()
        state.set_selection({0, 1})
        with qtbot.waitSignal(state.selection_changed, timeout=500):
            state.clear()
        assert state.is_empty()

    def test_clear_when_empty_no_emit(self, qtbot: QtBot) -> None:
        state = SelectionState()
        received = []
        state.selection_changed.connect(lambda s: received.append(s))
        state.clear()
        assert received == []
