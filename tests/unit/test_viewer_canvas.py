"""Tests for vispy canvas rendering."""

import numpy as np
import pytest


def _make_canvas():
    """Create a VispyCanvas, skipping if display is unavailable."""
    try:
        from squid_tools.viewer.canvas import VispyCanvas

        return VispyCanvas()
    except Exception as e:
        pytest.skip(f"vispy canvas requires display: {e}")


class TestVispyCanvas:
    def test_instantiate(self) -> None:
        canvas = _make_canvas()
        assert canvas is not None

    def test_set_image(self) -> None:
        canvas = _make_canvas()
        frame = np.random.rand(128, 128).astype(np.float32)
        canvas.set_image(frame)
        assert canvas.has_image()

    def test_set_image_with_colormap(self) -> None:
        canvas = _make_canvas()
        frame = np.random.rand(128, 128).astype(np.float32)
        canvas.set_image(frame, cmap="viridis")
        assert canvas.has_image()

    def test_clear(self) -> None:
        canvas = _make_canvas()
        frame = np.random.rand(128, 128).astype(np.float32)
        canvas.set_image(frame)
        canvas.clear_images()
        assert not canvas.has_image()

    def test_add_tile(self) -> None:
        canvas = _make_canvas()
        frame = np.random.rand(64, 64).astype(np.float32)
        canvas.add_tile(frame, x_mm=0.0, y_mm=0.0, width_mm=0.064, height_mm=0.064, tile_id="fov_0")
        canvas.add_tile(frame, x_mm=0.1, y_mm=0.0, width_mm=0.064, height_mm=0.064, tile_id="fov_1")
        assert canvas.tile_count() == 2

    def test_clear_tiles(self) -> None:
        canvas = _make_canvas()
        frame = np.random.rand(64, 64).astype(np.float32)
        canvas.add_tile(frame, x_mm=0.0, y_mm=0.0, width_mm=0.064, height_mm=0.064, tile_id="fov_0")
        canvas.clear_images()
        assert canvas.tile_count() == 0

    def test_add_border(self) -> None:
        canvas = _make_canvas()
        canvas.add_border(x_mm=0.0, y_mm=0.0, width_mm=0.064, height_mm=0.064, border_id="b0")
        assert canvas.border_count() == 1

    def test_set_borders_visible(self) -> None:
        canvas = _make_canvas()
        canvas.add_border(x_mm=0.0, y_mm=0.0, width_mm=0.064, height_mm=0.064, border_id="b0")
        canvas.set_borders_visible(False)
        canvas.set_borders_visible(True)
        # No crash = pass

    def test_fit_view(self) -> None:
        canvas = _make_canvas()
        frame = np.random.rand(128, 128).astype(np.float32)
        canvas.set_image(frame)
        canvas.fit_view()
        # No crash = pass

    def test_uint16_normalization(self) -> None:
        canvas = _make_canvas()
        frame = np.random.randint(0, 4095, (128, 128), dtype=np.uint16)
        canvas.set_image(frame)
        assert canvas.has_image()

    def test_native_widget(self) -> None:
        canvas = _make_canvas()
        widget = canvas.native_widget()
        assert widget is not None
