"""Tests for Viewer3DWidget (headless)."""

from __future__ import annotations

from pathlib import Path


class TestViewer3DWidget:
    def test_instantiate_no_acquisition(self, qtbot) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine
        from squid_tools.viewer.widget_3d import Viewer3DWidget

        engine = ViewportEngine()
        widget = Viewer3DWidget(engine, channel_names=["Ch A", "Ch B"])
        try:
            qtbot.addWidget(widget)
            assert widget is not None
            # No engine load → reload_volume should be a no-op
            widget._reload_volume()
        finally:
            widget.close()

    def test_instantiate_with_acquisition(
        self, qtbot, individual_acquisition: Path,
    ) -> None:
        from squid_tools.viewer.viewport_engine import ViewportEngine
        from squid_tools.viewer.widget_3d import Viewer3DWidget

        engine = ViewportEngine()
        engine.load(individual_acquisition, region="0")
        channel_names = [ch.name for ch in engine._acquisition.channels]
        widget = Viewer3DWidget(engine, channel_names=channel_names)
        try:
            qtbot.addWidget(widget)
            # FOV spinner range is set from engine.all_fov_indices()
            assert widget._fov_spin.minimum() >= 0
            assert len(widget._channel_checks) == len(channel_names)
        finally:
            widget.close()
