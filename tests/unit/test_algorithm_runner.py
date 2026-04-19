"""Tests for AlgorithmRunner."""

import logging
from pathlib import Path

import numpy as np
from pydantic import BaseModel
from pytestqt.qtbot import QtBot

from squid_tools.core.data_model import Acquisition
from squid_tools.gui.algorithm_runner import AlgorithmRunner
from squid_tools.processing.base import ProcessingPlugin
from squid_tools.viewer.viewport_engine import ViewportEngine
from tests.fixtures.generate_fixtures import create_individual_acquisition


class _Params(BaseModel):
    pass


class _InstantPlugin(ProcessingPlugin):
    name = "Instant"
    category = "correction"
    requires_gpu = False

    def parameters(self) -> type[BaseModel]:
        return _Params

    def validate(self, acq: Acquisition) -> list[str]:
        return []

    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        return frames

    def default_params(self, optical) -> BaseModel:
        return _Params()

    def test_cases(self) -> list[dict]:
        return []


class _FailingPlugin(_InstantPlugin):
    name = "Failing"

    def run_live(self, selection, engine, params, progress):
        raise RuntimeError("boom")


class TestAlgorithmRunner:
    def test_run_emits_complete(self, qtbot: QtBot, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = _InstantPlugin()
        runner = AlgorithmRunner()

        with qtbot.waitSignal(runner.run_complete, timeout=5000):
            runner.run(plugin=plugin, selection={0, 1}, engine=engine, params=_Params())

    def test_run_emits_progress(self, qtbot: QtBot, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = _InstantPlugin()
        runner = AlgorithmRunner()

        progress_calls: list[tuple] = []
        runner.progress_updated.connect(lambda *a: progress_calls.append(a))

        with qtbot.waitSignal(runner.run_complete, timeout=5000):
            runner.run(plugin=plugin, selection={0, 1}, engine=engine, params=_Params())

        assert len(progress_calls) >= 1

    def test_run_failure_emits_run_failed(self, qtbot: QtBot, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = _FailingPlugin()
        runner = AlgorithmRunner()

        with qtbot.waitSignal(runner.run_failed, timeout=5000) as blocker:
            runner.run(plugin=plugin, selection={0}, engine=engine, params=_Params())
        # First arg is plugin_name, second is error message
        assert blocker.args[0] == "Failing"
        assert "boom" in blocker.args[1]

    def test_second_run_while_busy_is_rejected(self, qtbot: QtBot, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        plugin = _InstantPlugin()
        runner = AlgorithmRunner()

        # Kick off first run
        runner.run(plugin=plugin, selection={0}, engine=engine, params=_Params())
        # Second run immediately after should return False
        accepted = runner.run(plugin=plugin, selection={1}, engine=engine, params=_Params())
        assert accepted is False
        qtbot.waitUntil(lambda: not runner.is_running(), timeout=5000)


class TestAlgorithmRunnerLogging:
    def test_run_emits_info_log(self, qtbot, monkeypatch, caplog):
        from squid_tools.gui.algorithm_runner import AlgorithmRunner

        runner = AlgorithmRunner()
        caplog.set_level(logging.INFO, logger="squid_tools")

        class FakePlugin:
            name = "FakePlugin"
            def run_live(self, selection, engine, params, progress):
                progress("phase", 1, 1)

        started = runner.run(
            plugin=FakePlugin(),
            selection=None,
            engine=object(),
            params=object(),
        )
        assert started is True
        qtbot.waitUntil(lambda: not runner.is_running(), timeout=2000)

        infos = [
            r for r in caplog.records
            if r.name.startswith("squid_tools.gui.algorithm_runner")
            and r.levelno == logging.INFO
        ]
        assert any("FakePlugin" in r.getMessage() for r in infos)
