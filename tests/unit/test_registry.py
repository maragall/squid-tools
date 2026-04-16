"""Tests for plugin ABC and registry."""

import numpy as np
from pydantic import BaseModel

from squid_tools.core.data_model import (
    Acquisition,
    AcquisitionFormat,
    AcquisitionMode,
    FOVPosition,
    ObjectiveMetadata,
    OpticalMetadata,
)
from squid_tools.core.registry import PluginRegistry
from squid_tools.processing.base import ProcessingPlugin


class DummyParams(BaseModel):
    sigma: float = 1.0


class DummyPlugin(ProcessingPlugin):
    name = "Dummy"
    category = "correction"
    requires_gpu = False

    def parameters(self) -> type[BaseModel]:
        return DummyParams

    def validate(self, acq: Acquisition) -> list[str]:
        return []

    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        return frames

    def default_params(self, optical: OpticalMetadata) -> BaseModel:
        return DummyParams()

    def test_cases(self) -> list[dict]:
        return [{"input": np.ones((10, 10)), "expected": np.ones((10, 10))}]


class TestProcessingPlugin:
    def test_instantiate_plugin(self) -> None:
        plugin = DummyPlugin()
        assert plugin.name == "Dummy"
        assert plugin.category == "correction"
        assert plugin.requires_gpu is False

    def test_parameters_returns_model_class(self) -> None:
        plugin = DummyPlugin()
        assert plugin.parameters() is DummyParams

    def test_validate_returns_list(self) -> None:
        plugin = DummyPlugin()
        acq = Acquisition(
            path="/tmp/test",
            format=AcquisitionFormat.INDIVIDUAL_IMAGES,
            mode=AcquisitionMode.WELLPLATE,
            objective=ObjectiveMetadata(name="20x", magnification=20.0, pixel_size_um=0.325),
        )
        warnings = plugin.validate(acq)
        assert isinstance(warnings, list)

    def test_process_returns_array(self) -> None:
        plugin = DummyPlugin()
        arr = np.ones((10, 10), dtype=np.uint16)
        result = plugin.process(arr, DummyParams())
        assert isinstance(result, np.ndarray)

    def test_default_params(self) -> None:
        plugin = DummyPlugin()
        params = plugin.default_params(OpticalMetadata())
        assert isinstance(params, DummyParams)

    def test_test_cases_returns_list(self) -> None:
        plugin = DummyPlugin()
        cases = plugin.test_cases()
        assert len(cases) > 0


class TestPluginRegistry:
    def test_register_and_get(self) -> None:
        registry = PluginRegistry()
        plugin = DummyPlugin()
        registry.register(plugin)
        assert registry.get("Dummy") is plugin

    def test_get_missing_returns_none(self) -> None:
        registry = PluginRegistry()
        assert registry.get("missing") is None

    def test_list_plugins(self) -> None:
        registry = PluginRegistry()
        registry.register(DummyPlugin())
        names = registry.list_names()
        assert "Dummy" in names

    def test_list_by_category(self) -> None:
        registry = PluginRegistry()
        registry.register(DummyPlugin())
        correction_plugins = registry.list_by_category("correction")
        assert len(correction_plugins) == 1
        assert correction_plugins[0].name == "Dummy"

    def test_list_empty_category(self) -> None:
        registry = PluginRegistry()
        registry.register(DummyPlugin())
        assert registry.list_by_category("stitching") == []


class TestProcessRegion:
    def test_default_process_region_returns_none(self) -> None:
        plugin = DummyPlugin()
        result = plugin.process_region(
            frames={0: np.ones((10, 10))},
            positions=[FOVPosition(fov_index=0, x_mm=0.0, y_mm=0.0)],
            params=DummyParams(),
        )
        assert result is None
