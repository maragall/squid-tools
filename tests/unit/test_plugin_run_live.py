"""Tests for ProcessingPlugin.run_live() default implementation."""

from pathlib import Path

import numpy as np
from pydantic import BaseModel

from squid_tools.core.data_model import Acquisition
from squid_tools.processing.base import ProcessingPlugin
from squid_tools.viewer.viewport_engine import ViewportEngine
from tests.fixtures.generate_fixtures import create_individual_acquisition


class NoopParams(BaseModel):
    pass


class NoopPlugin(ProcessingPlugin):
    name = "Noop"
    category = "correction"
    requires_gpu = False

    def parameters(self) -> type[BaseModel]:
        return NoopParams

    def validate(self, acq: Acquisition) -> list[str]:
        return []

    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        return frames  # identity

    def default_params(self, optical) -> BaseModel:
        return NoopParams()

    def test_cases(self) -> list[dict]:
        return []


class TestRunLiveDefault:
    def test_run_live_exists(self) -> None:
        plugin = NoopPlugin()
        assert hasattr(plugin, "run_live")

    def test_run_live_calls_progress(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = NoopPlugin()

        calls = []

        def progress(phase: str, cur: int, total: int) -> None:
            calls.append((phase, cur, total))

        plugin.run_live(
            selection={0, 1},
            engine=engine,
            params=NoopParams(),
            progress=progress,
        )
        # At least one progress call, last current equals total
        assert len(calls) >= 1
        last = calls[-1]
        assert last[1] == last[2]

    def test_run_live_none_selection_uses_all(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = NoopPlugin()

        calls = []
        def progress(phase: str, cur: int, total: int) -> None:
            calls.append((phase, cur, total))

        plugin.run_live(
            selection=None, engine=engine,
            params=NoopParams(), progress=progress,
        )
        # Total should equal 4 (nx*ny for 2x2 grid)
        assert calls[-1][2] == 4
