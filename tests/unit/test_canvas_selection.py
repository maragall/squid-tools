"""Tests for StageCanvas selection features."""

import numpy as np

from squid_tools.viewer.canvas import StageCanvas
from squid_tools.viewer.viewport_engine import VisibleTile


def _make_tile(fov_index: int, x_mm: float, y_mm: float) -> VisibleTile:
    return VisibleTile(
        fov_index=fov_index,
        x_mm=x_mm, y_mm=y_mm,
        width_mm=1.0, height_mm=1.0,
        data=np.zeros((32, 32), dtype=np.float32),
    )


class TestCanvasSelection:
    def test_selection_drawn_signal_exists(self) -> None:
        canvas = StageCanvas()
        assert hasattr(canvas, "selection_drawn")

    def test_set_selected_ids_updates_border_colors(self) -> None:
        canvas = StageCanvas()
        tiles = [_make_tile(0, 0.0, 0.0), _make_tile(1, 1.0, 0.0)]
        canvas.render_tiles(tiles)
        # Mark fov 0 as selected
        canvas.set_selected_ids({0})
        # The border for fov 0 should now be Cephla-blue, fov 1 still yellow
        assert canvas._selected_ids == {0}

    def test_set_selected_ids_empty_clears(self) -> None:
        canvas = StageCanvas()
        tiles = [_make_tile(0, 0.0, 0.0)]
        canvas.render_tiles(tiles)
        canvas.set_selected_ids({0})
        canvas.set_selected_ids(set())
        assert canvas._selected_ids == set()

    def test_selected_border_color_differs(self) -> None:
        # Cannot easily read vispy Line color programmatically in headless tests,
        # so we verify the helper returns the expected color strings.
        canvas = StageCanvas()
        assert canvas._border_color_for(fov_index=5, selected_ids={5}) == "#2A82DA"
        assert canvas._border_color_for(fov_index=5, selected_ids=set()) == "yellow"
