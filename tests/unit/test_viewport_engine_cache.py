"""Tests for ViewportEngine's split-cache architecture.

After the cache split (see
docs/superpowers/specs/2026-04-26-viewer-cache-split-design.md), clim
changes must hit the processed-tile cache without reloading raw data, and
pipeline changes must invalidate both layers.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from squid_tools.viewer.viewport_engine import ViewportEngine
from tests.fixtures.generate_fixtures import create_individual_acquisition


def _setup_engine(tmp_path: Path) -> tuple[ViewportEngine, list[str]]:
    acq_path = create_individual_acquisition(
        tmp_path / "acq", nx=2, ny=2, nz=1, nc=2, nt=1,
    )
    engine = ViewportEngine()
    engine.load(acq_path, region="0")
    channel_names = [
        ch.name for ch in engine._acquisition.channels  # type: ignore[union-attr]
    ]
    return engine, channel_names


class TestRenderCacheHitsOnClimChange:
    """Changing clims must miss render cache but hit processed cache."""

    def test_clim_change_does_not_reload_raw(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        engine, names = _setup_engine(tmp_path)
        bb = engine.bounding_box()

        # Track _load_raw calls
        original_load = engine._load_raw
        load_calls: list[tuple[int, int, int, int]] = []

        def counting_load(fov: int, z: int, channel: int, timepoint: int):
            load_calls.append((fov, z, channel, timepoint))
            return original_load(fov, z, channel, timepoint)

        monkeypatch.setattr(engine, "_load_raw", counting_load)

        # First render: cold caches
        clims_a = {0: (0.0, 100.0), 1: (0.0, 100.0)}
        engine.get_composite_tiles(
            viewport=bb, screen_width=800, screen_height=600,
            active_channels=[0, 1], channel_names=names,
            channel_clims=clims_a, z=0, timepoint=0, level_override=0,
        )
        first_loads = list(load_calls)
        assert first_loads, "first render should call _load_raw"

        # Second render with different clims: render cache misses
        # (clim_sig changed) but processed cache hits.
        clims_b = {0: (0.0, 50.0), 1: (0.0, 50.0)}
        load_calls.clear()
        engine.get_composite_tiles(
            viewport=bb, screen_width=800, screen_height=600,
            active_channels=[0, 1], channel_names=names,
            channel_clims=clims_b, z=0, timepoint=0, level_override=0,
        )
        assert load_calls == [], (
            f"clim change must not reload raw frames; got {load_calls}"
        )


class TestProcessedCacheInvalidatesOnPipelineChange:
    """set_pipeline drops both caches; next render reloads."""

    def test_pipeline_change_clears_processed_cache(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        engine, names = _setup_engine(tmp_path)
        bb = engine.bounding_box()

        clims = {0: (0.0, 100.0), 1: (0.0, 100.0)}
        engine.get_composite_tiles(
            viewport=bb, screen_width=800, screen_height=600,
            active_channels=[0, 1], channel_names=names,
            channel_clims=clims, z=0, timepoint=0, level_override=0,
        )
        assert engine._processed_tile_cache.current_bytes > 0
        assert engine._render_cache.current_bytes > 0

        # Setting a pipeline (even an empty no-op transform list change)
        # must invalidate both caches.
        engine.set_pipeline([lambda x: x.astype(np.float32)])
        assert engine._processed_tile_cache.current_bytes == 0
        assert engine._render_cache.current_bytes == 0

        # Track raw loads on the second render to confirm a true reload.
        original_load = engine._load_raw
        load_calls: list[tuple[int, int, int, int]] = []

        def counting_load(fov: int, z: int, channel: int, timepoint: int):
            load_calls.append((fov, z, channel, timepoint))
            return original_load(fov, z, channel, timepoint)

        monkeypatch.setattr(engine, "_load_raw", counting_load)
        engine.get_composite_tiles(
            viewport=bb, screen_width=800, screen_height=600,
            active_channels=[0, 1], channel_names=names,
            channel_clims=clims, z=0, timepoint=0, level_override=0,
        )
        assert load_calls, "pipeline change must force a reload"


class TestChannelToggleKeepsProcessedTiles:
    """Toggling a channel off and back on must not reload it."""

    def test_channel_toggle_round_trip_no_reload(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        engine, names = _setup_engine(tmp_path)
        bb = engine.bounding_box()

        clims = {0: (0.0, 100.0), 1: (0.0, 100.0)}
        # Render with both channels: warms processed cache for both.
        engine.get_composite_tiles(
            viewport=bb, screen_width=800, screen_height=600,
            active_channels=[0, 1], channel_names=names,
            channel_clims=clims, z=0, timepoint=0, level_override=0,
        )

        # Track loads from now on
        original_load = engine._load_raw
        load_calls: list[tuple[int, int, int, int]] = []

        def counting_load(fov: int, z: int, channel: int, timepoint: int):
            load_calls.append((fov, z, channel, timepoint))
            return original_load(fov, z, channel, timepoint)

        monkeypatch.setattr(engine, "_load_raw", counting_load)

        # Render with channel 1 off: render cache misses (different
        # active-channels signature) but processed cache for channel 0
        # is still warm.
        engine.get_composite_tiles(
            viewport=bb, screen_width=800, screen_height=600,
            active_channels=[0], channel_names=names,
            channel_clims=clims, z=0, timepoint=0, level_override=0,
        )
        assert load_calls == [], (
            f"channel-off toggle must not reload visible channels; got {load_calls}"
        )

        # Toggle channel 1 back on: still no reload because both processed
        # tiles remained in cache.
        engine.get_composite_tiles(
            viewport=bb, screen_width=800, screen_height=600,
            active_channels=[0, 1], channel_names=names,
            channel_clims=clims, z=0, timepoint=0, level_override=0,
        )
        assert load_calls == [], (
            f"channel-on toggle must reuse processed tiles; got {load_calls}"
        )
