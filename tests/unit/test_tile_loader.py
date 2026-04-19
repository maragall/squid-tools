"""Unit tests for the async tile loader."""

from __future__ import annotations

import dataclasses
import logging
import threading
import time

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
        with pytest.raises(dataclasses.FrozenInstanceError):
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


class TestAsyncTileLoaderRequest:
    def _request_kwargs(self, **overrides):
        base = dict(
            viewport=(0.0, 0.0, 1.0, 1.0),
            screen_width=100,
            screen_height=100,
            active_channels=[0],
            channel_names=["C1"],
            channel_clims={0: (0.0, 1.0)},
            z=0,
            timepoint=0,
        )
        base.update(overrides)
        return base

    def test_request_returns_id_and_emits_tiles_ready(self, qtbot: QtBot) -> None:
        engine = _FakeEngine()
        loader = AsyncTileLoader(engine)
        try:
            with qtbot.waitSignal(loader.tiles_ready, timeout=2000) as blocker:
                request_id = loader.request(**self._request_kwargs())
            emitted_id, tiles = blocker.args
            assert emitted_id == request_id
            assert len(tiles) == 1
            assert len(engine.calls) == 1
            assert engine.calls[0]["viewport"] == (0.0, 0.0, 1.0, 1.0)
        finally:
            loader.stop()

    def test_request_ids_increment(self, qtbot: QtBot) -> None:
        engine = _FakeEngine()
        loader = AsyncTileLoader(engine)
        try:
            id1 = loader.request(**self._request_kwargs())
            id2 = loader.request(**self._request_kwargs())
            assert id2 == id1 + 1
        finally:
            loader.stop()

    def test_request_failure_emits_request_failed(self, qtbot: QtBot) -> None:
        class BrokenEngine:
            def get_composite_tiles(self, **kwargs):
                raise RuntimeError("boom")

        loader = AsyncTileLoader(BrokenEngine())
        try:
            with qtbot.waitSignal(
                loader.request_failed, timeout=2000,
            ) as blocker:
                loader.request(**self._request_kwargs())
            emitted_id, err = blocker.args
            assert emitted_id == 1
            assert "boom" in err
        finally:
            loader.stop()


class TestAsyncTileLoaderReplaceSemantics:
    def test_rapid_requests_last_one_wins(self, qtbot: QtBot) -> None:
        barrier = threading.Event()
        received = []

        class SlowEngine:
            def __init__(self):
                self.call_count = 0

            def get_composite_tiles(self, **kwargs):
                self.call_count += 1
                # First call blocks until barrier fires, second returns instantly
                if self.call_count == 1:
                    barrier.wait(timeout=2.0)
                return [("tile", kwargs["viewport"], self.call_count)]

        engine = SlowEngine()
        loader = AsyncTileLoader(engine)
        loader.tiles_ready.connect(
            lambda rid, tiles: received.append((rid, tiles)),
        )
        try:
            id_a = loader.request(
                viewport=(0.0, 0.0, 1.0, 1.0),
                screen_width=100, screen_height=100,
                active_channels=[0], channel_names=["C1"],
                channel_clims={0: (0.0, 1.0)},
                z=0, timepoint=0,
            )
            # Wait briefly so worker picks up A
            time.sleep(0.1)
            id_b = loader.request(
                viewport=(2.0, 2.0, 3.0, 3.0),
                screen_width=100, screen_height=100,
                active_channels=[0], channel_names=["C1"],
                channel_clims={0: (0.0, 1.0)},
                z=0, timepoint=0,
            )
            barrier.set()
            qtbot.waitUntil(
                lambda: any(rid == id_b for rid, _ in received), timeout=3000,
            )
            ids = [rid for rid, _ in received]
            assert id_a in ids
            assert id_b in ids
            b_tiles = next(t for rid, t in received if rid == id_b)
            assert b_tiles[0][2] == 2
        finally:
            loader.stop()
