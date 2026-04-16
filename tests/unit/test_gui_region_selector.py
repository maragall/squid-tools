"""Tests for region selector widget."""

from pytestqt.qtbot import QtBot

from squid_tools.core.data_model import (
    Acquisition,
    AcquisitionFormat,
    AcquisitionMode,
    FOVPosition,
    ObjectiveMetadata,
    Region,
)
from squid_tools.gui.region_selector import RegionSelector


def _make_wellplate_acquisition() -> Acquisition:
    regions = {
        "A1": Region(
            region_id="A1",
            center_mm=(10.0, 10.0, 0.0),
            fovs=[FOVPosition(fov_index=0, x_mm=10.0, y_mm=10.0)],
        ),
        "A2": Region(
            region_id="A2",
            center_mm=(20.0, 10.0, 0.0),
            fovs=[FOVPosition(fov_index=0, x_mm=20.0, y_mm=10.0)],
        ),
        "B1": Region(
            region_id="B1",
            center_mm=(10.0, 20.0, 0.0),
            fovs=[FOVPosition(fov_index=0, x_mm=10.0, y_mm=20.0)],
        ),
    }
    return Acquisition(
        path="/tmp/test",
        format=AcquisitionFormat.INDIVIDUAL_IMAGES,
        mode=AcquisitionMode.WELLPLATE,
        objective=ObjectiveMetadata(name="20x", magnification=20.0, pixel_size_um=0.325),
        regions=regions,
    )


def _make_tissue_acquisition() -> Acquisition:
    regions = {
        "manual0": Region(
            region_id="manual0",
            center_mm=(5.0, 5.0, 0.0),
            fovs=[FOVPosition(fov_index=0, x_mm=5.0, y_mm=5.0)],
        ),
        "manual1": Region(
            region_id="manual1",
            center_mm=(15.0, 15.0, 0.0),
            fovs=[FOVPosition(fov_index=0, x_mm=15.0, y_mm=15.0)],
        ),
    }
    return Acquisition(
        path="/tmp/test",
        format=AcquisitionFormat.INDIVIDUAL_IMAGES,
        mode=AcquisitionMode.MANUAL,
        objective=ObjectiveMetadata(name="20x", magnification=20.0, pixel_size_um=0.325),
        regions=regions,
    )


class TestRegionSelector:
    def test_instantiate(self, qtbot: QtBot) -> None:
        selector = RegionSelector()
        qtbot.addWidget(selector)
        assert selector is not None

    def test_load_wellplate(self, qtbot: QtBot) -> None:
        selector = RegionSelector()
        qtbot.addWidget(selector)
        acq = _make_wellplate_acquisition()
        selector.load_acquisition(acq)
        assert selector.is_wellplate_mode()

    def test_load_tissue(self, qtbot: QtBot) -> None:
        selector = RegionSelector()
        qtbot.addWidget(selector)
        acq = _make_tissue_acquisition()
        selector.load_acquisition(acq)
        assert not selector.is_wellplate_mode()

    def test_region_selected_signal(self, qtbot: QtBot) -> None:
        selector = RegionSelector()
        qtbot.addWidget(selector)
        acq = _make_tissue_acquisition()
        selector.load_acquisition(acq)
        with qtbot.waitSignal(selector.region_selected, timeout=1000):
            selector.select_region("manual0")

    def test_selected_region_id(self, qtbot: QtBot) -> None:
        selector = RegionSelector()
        qtbot.addWidget(selector)
        acq = _make_tissue_acquisition()
        selector.load_acquisition(acq)
        selector.select_region("manual0")
        assert selector.selected_region_id() == "manual0"
