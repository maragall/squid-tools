"""Tests for StitcherPlugin.run_live()."""

import logging
from pathlib import Path

from squid_tools.processing.stitching.plugin import StitcherParams, StitcherPlugin
from squid_tools.viewer.viewport_engine import ViewportEngine
from tests.fixtures.generate_fixtures import create_individual_acquisition


class TestStitcherRunLive:
    def test_run_live_emits_phases(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = StitcherPlugin()
        # pixel_size_um is required; derive from the loaded acquisition.
        params = StitcherParams(pixel_size_um=engine.pixel_size_um)

        phases: list[str] = []
        def progress(phase, cur, total):
            phases.append(phase)

        plugin.run_live(
            selection={0, 1, 2, 3}, engine=engine,
            params=params, progress=progress,
        )
        # Expect at least "Finding pairs" and "Registering" phases
        assert any("Finding pairs" in p for p in phases)
        # Registration phase emits per-pair progress
        assert any("Registering" in p or "Optimizing" in p for p in phases)


class TestStitcherLogging:
    def test_run_live_emits_info_log(
        self, qtbot, individual_acquisition, caplog,
    ):
        from squid_tools.processing.stitching.plugin import StitcherPlugin
        from squid_tools.viewer.viewport_engine import ViewportEngine

        caplog.set_level(logging.INFO, logger="squid_tools")
        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")
        plugin = StitcherPlugin()
        # default_params requires OpticalMetadata now — mirror what the app does
        params = plugin.default_params(engine._acquisition.optical)

        def noop_progress(phase: str, current: int, total: int) -> None:
            pass

        plugin.run_live(
            selection=None,
            engine=engine,
            params=params,
            progress=noop_progress,
        )
        infos = [
            r for r in caplog.records
            if r.name.startswith("squid_tools.processing.stitching")
            and r.levelno == logging.INFO
        ]
        assert infos, "Stitcher run_live should log INFO phase transitions"
