"""Tests for AppController."""

import logging
from pathlib import Path

import pytest

from squid_tools.core.data_model import AcquisitionFormat
from squid_tools.gui.controller import AppController
from tests.fixtures.generate_fixtures import create_individual_acquisition


class TestAppController:
    def test_load_acquisition(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        ctrl = AppController()
        ctrl.load_acquisition(acq_path)
        assert ctrl.acquisition is not None
        assert ctrl.acquisition.format == AcquisitionFormat.INDIVIDUAL_IMAGES

    def test_load_sets_regions(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        ctrl = AppController()
        ctrl.load_acquisition(acq_path)
        assert len(ctrl.acquisition.regions) > 0

    def test_get_frame(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        ctrl = AppController()
        ctrl.load_acquisition(acq_path)
        frame = ctrl.get_frame(region="0", fov=0, z=0, channel=0, timepoint=0)
        assert frame.shape == (128, 128)

    def test_get_region_frames(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        ctrl = AppController()
        ctrl.load_acquisition(acq_path)
        frames = ctrl.get_region_frames(region="0", z=0, channel=0, timepoint=0)
        assert len(frames) == 4  # 2x2 FOVs
        assert all(f.shape == (128, 128) for f in frames.values())

    def test_run_plugin_on_frame(self, tmp_path: Path) -> None:
        import numpy as np
        from pydantic import BaseModel

        from squid_tools.processing.base import ProcessingPlugin

        class AddParams(BaseModel):
            value: int = 10

        class AddPlugin(ProcessingPlugin):
            name = "Add"
            category = "correction"

            def parameters(self):
                return AddParams

            def validate(self, acq):
                return []

            def process(self, frames, params):
                return frames + params.value

            def default_params(self, optical):
                return AddParams()

            def test_cases(self):
                return []

        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        ctrl = AppController()
        ctrl.registry.register(AddPlugin())
        ctrl.load_acquisition(acq_path)
        frame = ctrl.get_frame(region="0", fov=0, z=0, channel=0, timepoint=0)
        result = ctrl.run_plugin("Add", frame)
        assert np.all(result == frame + 10)


class TestControllerLogging:
    def test_load_emits_info_log(self, tmp_path, individual_acquisition, caplog):
        from squid_tools.gui.controller import AppController

        controller = AppController()
        caplog.set_level(logging.INFO, logger="squid_tools")
        controller.load_acquisition(individual_acquisition)
        messages = [
            r.getMessage() for r in caplog.records
            if r.name.startswith("squid_tools.gui.controller")
        ]
        assert any("Loaded acquisition" in m for m in messages)

    def test_load_failure_emits_error_log(self, tmp_path, caplog):
        from squid_tools.gui.controller import AppController

        controller = AppController()
        caplog.set_level(logging.ERROR, logger="squid_tools")
        with pytest.raises(ValueError):
            controller.load_acquisition(tmp_path / "does_not_exist")
        errors = [
            r for r in caplog.records
            if r.name.startswith("squid_tools.gui.controller")
            and r.levelno == logging.ERROR
        ]
        assert errors, "controller should log ERROR on failure"
