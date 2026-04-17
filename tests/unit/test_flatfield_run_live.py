"""Tests for FlatfieldPlugin.run_live()."""

from pathlib import Path

from squid_tools.processing.flatfield.plugin import FlatfieldPlugin, FlatfieldParams
from squid_tools.viewer.viewport_engine import ViewportEngine
from tests.fixtures.generate_fixtures import create_individual_acquisition


class TestFlatfieldRunLive:
    def test_run_live_emits_calibrate_phase(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = FlatfieldPlugin()
        params = FlatfieldParams()

        phases: list[str] = []
        def progress(phase, cur, total):
            phases.append(phase)

        plugin.run_live(
            selection={0, 1, 2, 3}, engine=engine,
            params=params, progress=progress,
        )
        assert any("Calibrat" in p for p in phases)
        assert any("Apply" in p for p in phases)

    def test_run_live_installs_pipeline(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = FlatfieldPlugin()
        params = FlatfieldParams()

        def progress(phase, cur, total): pass

        # Before run: pipeline empty
        assert len(engine._pipeline) == 0
        plugin.run_live(
            selection=None, engine=engine, params=params, progress=progress,
        )
        # After run: pipeline has one transform installed
        assert len(engine._pipeline) >= 1
