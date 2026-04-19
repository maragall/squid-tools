"""Unit tests for the async tile loader."""

from __future__ import annotations

import logging

import pytest
from pytestqt.qtbot import QtBot

from squid_tools.viewer.tile_loader import AsyncTileLoader, TileRequest


@pytest.fixture(autouse=True)
def _reset_root_logger():
    root = logging.getLogger("squid_tools")
    saved = list(root.handlers)
    yield
    for h in list(root.handlers):
        root.removeHandler(h)
    for h in saved:
        root.addHandler(h)


class _FakeEngine:
    def __init__(self):
        self.calls = []

    def get_composite_tiles(self, **kwargs):
        self.calls.append(kwargs)
        viewport = kwargs["viewport"]
        return [("tile", viewport)]


class TestTileRequest:
    def test_is_frozen_dataclass(self) -> None:
        req = TileRequest(
            request_id=1,
            viewport=(0.0, 0.0, 1.0, 1.0),
            screen_width=100,
            screen_height=100,
            active_channels=[0],
            channel_names=["C1"],
            channel_clims={0: (0.0, 1.0)},
            z=0,
            timepoint=0,
        )
        assert req.request_id == 1
        with pytest.raises(Exception):
            req.request_id = 2  # frozen


class TestAsyncTileLoaderConstruction:
    def test_starts_worker_thread(self, qtbot: QtBot) -> None:
        engine = _FakeEngine()
        loader = AsyncTileLoader(engine)
        try:
            assert loader._thread.isRunning()
        finally:
            loader.stop()

    def test_stop_quits_thread(self, qtbot: QtBot) -> None:
        engine = _FakeEngine()
        loader = AsyncTileLoader(engine)
        loader.stop()
        assert not loader._thread.isRunning()
