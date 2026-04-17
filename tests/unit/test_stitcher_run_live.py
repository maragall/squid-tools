"""Tests for StitcherPlugin.run_live()."""

from pathlib import Path

from squid_tools.processing.stitching.plugin import StitcherPlugin, StitcherParams
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
        params = StitcherParams()

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
