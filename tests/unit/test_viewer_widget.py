"""Tests for the continuous zoom ViewerWidget."""

from pathlib import Path

from pytestqt.qtbot import QtBot

from squid_tools.viewer.widget import ViewerWidget
from tests.fixtures.generate_fixtures import create_individual_acquisition


class TestViewerWidget:
    def test_instantiate(self, qtbot: QtBot) -> None:
        widget = ViewerWidget()
        qtbot.addWidget(widget)
        assert widget is not None

    def test_has_channel_slider(self, qtbot: QtBot) -> None:
        widget = ViewerWidget()
        qtbot.addWidget(widget)
        assert widget.channel_slider is not None

    def test_has_z_slider(self, qtbot: QtBot) -> None:
        widget = ViewerWidget()
        qtbot.addWidget(widget)
        assert widget.z_slider is not None

    def test_has_t_slider(self, qtbot: QtBot) -> None:
        widget = ViewerWidget()
        qtbot.addWidget(widget)
        assert widget.t_slider is not None

    def test_fov_clicked_signal_exists(self, qtbot: QtBot) -> None:
        widget = ViewerWidget()
        qtbot.addWidget(widget)
        received = []
        widget.fov_clicked.connect(lambda r, f: received.append((r, f)))
        widget.fov_clicked.emit("A1", 3)
        assert received == [("A1", 3)]

    def test_set_borders_visible(self, qtbot: QtBot) -> None:
        widget = ViewerWidget()
        qtbot.addWidget(widget)
        widget.set_borders_visible(False)
        widget.set_borders_visible(True)

    def test_load_acquisition(self, qtbot: QtBot, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        widget = ViewerWidget()
        qtbot.addWidget(widget)
        widget.load_acquisition(acq_path, region="0")
        assert widget._engine.is_loaded()

    def test_load_acquisition_configures_sliders(self, qtbot: QtBot, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=2, nc=2, nt=1
        )
        widget = ViewerWidget()
        qtbot.addWidget(widget)
        widget.load_acquisition(acq_path, region="0")
        assert widget.channel_slider.maximum() == 1
        assert widget.z_slider.maximum() == 1

    def test_set_pipeline(self, qtbot: QtBot, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        widget = ViewerWidget()
        qtbot.addWidget(widget)
        widget.load_acquisition(acq_path, region="0")
        # Setting an empty pipeline should not crash
        widget.set_pipeline([])
