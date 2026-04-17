"""End-to-end test of shift+drag selection and border recoloring."""

from pathlib import Path

from pytestqt.qtbot import QtBot

from squid_tools.viewer.widget import ViewerWidget
from tests.fixtures.generate_fixtures import create_individual_acquisition


class TestSelectionWorkflow:
    def test_viewer_has_selection_state(self, qtbot: QtBot, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=3, ny=3, nz=1, nc=1, nt=1,
        )
        viewer = ViewerWidget()
        qtbot.addWidget(viewer)
        viewer.load_acquisition(acq_path, region="0")
        assert hasattr(viewer, "selection")

    def test_selection_drawn_updates_selection(self, qtbot: QtBot, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        viewer = ViewerWidget()
        qtbot.addWidget(viewer)
        viewer.load_acquisition(acq_path, region="0")

        # Pretend the canvas emitted a selection_drawn covering the entire stage
        bb = viewer._engine.bounding_box()
        viewer._on_selection_drawn(bb)
        # All 4 FOVs should now be selected
        assert viewer.selection.selected == {0, 1, 2, 3}

    def test_empty_rectangle_clears_selection(self, qtbot: QtBot, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        viewer = ViewerWidget()
        qtbot.addWidget(viewer)
        viewer.load_acquisition(acq_path, region="0")

        # First select all
        bb = viewer._engine.bounding_box()
        viewer._on_selection_drawn(bb)
        # Then draw rectangle that intersects no tiles (far away)
        viewer._on_selection_drawn((1000.0, 1000.0, 1001.0, 1001.0))
        assert viewer.selection.is_empty()
