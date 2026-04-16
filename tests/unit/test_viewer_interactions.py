"""Tests for viewer interaction events."""

import numpy as np
from pytestqt.qtbot import QtBot

from squid_tools.viewer.widget import ViewerWidget


class TestViewerInteractions:
    def test_fov_clicked_signal_exists(self, qtbot: QtBot) -> None:
        widget = ViewerWidget()
        qtbot.addWidget(widget)
        # Verify signal exists and is connectable
        received = []
        widget.fov_clicked.connect(lambda r, f: received.append((r, f)))
        # Manually emit to test signal works
        widget.fov_clicked.emit("A1", 3)
        assert received == [("A1", 3)]

    def test_get_tile_at_position(self) -> None:
        from squid_tools.viewer.canvas import VispyCanvas

        canvas = VispyCanvas()
        frame = np.random.rand(64, 64).astype(np.float32)
        canvas.add_tile(frame, x_mm=0.0, y_mm=0.0, width_mm=0.064, height_mm=0.064, tile_id="fov_0")
        canvas.add_tile(frame, x_mm=0.1, y_mm=0.0, width_mm=0.064, height_mm=0.064, tile_id="fov_1")
        # Point inside fov_0 (mm coordinates)
        tile_id = canvas.get_tile_at(x=0.032, y=0.032)
        assert tile_id == "fov_0"
        # Point inside fov_1
        tile_id = canvas.get_tile_at(x=0.132, y=0.032)
        assert tile_id == "fov_1"
        # Point outside all tiles
        tile_id = canvas.get_tile_at(x=5.0, y=5.0)
        assert tile_id is None
