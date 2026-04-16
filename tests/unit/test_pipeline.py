"""Tests for processing pipeline."""

import numpy as np
from pydantic import BaseModel

from squid_tools.core.data_model import Acquisition, OpticalMetadata
from squid_tools.core.pipeline import Pipeline
from squid_tools.processing.base import ProcessingPlugin


class AddOneParams(BaseModel):
    value: int = 1


class AddOnePlugin(ProcessingPlugin):
    name = "AddOne"
    category = "correction"

    def parameters(self) -> type[BaseModel]:
        return AddOneParams

    def validate(self, acq: Acquisition) -> list[str]:
        return []

    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        assert isinstance(params, AddOneParams)
        return frames + params.value

    def default_params(self, optical: OpticalMetadata) -> BaseModel:
        return AddOneParams()

    def test_cases(self) -> list[dict]:
        return []


class MultiplyParams(BaseModel):
    factor: int = 2


class MultiplyPlugin(ProcessingPlugin):
    name = "Multiply"
    category = "correction"

    def parameters(self) -> type[BaseModel]:
        return MultiplyParams

    def validate(self, acq: Acquisition) -> list[str]:
        return []

    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        assert isinstance(params, MultiplyParams)
        return frames * params.factor

    def default_params(self, optical: OpticalMetadata) -> BaseModel:
        return MultiplyParams()

    def test_cases(self) -> list[dict]:
        return []


class TestPipeline:
    def test_empty_pipeline(self) -> None:
        pipe = Pipeline()
        arr = np.ones((10, 10), dtype=np.uint16)
        result = pipe.run(arr)
        assert np.array_equal(result, arr)

    def test_single_step(self) -> None:
        pipe = Pipeline()
        pipe.add(AddOnePlugin(), AddOneParams(value=5))
        arr = np.zeros((10, 10), dtype=np.int32)
        result = pipe.run(arr)
        assert np.all(result == 5)

    def test_chained_steps(self) -> None:
        pipe = Pipeline()
        pipe.add(AddOnePlugin(), AddOneParams(value=3))
        pipe.add(MultiplyPlugin(), MultiplyParams(factor=2))
        arr = np.ones((10, 10), dtype=np.int32)
        result = pipe.run(arr)
        # (1 + 3) * 2 = 8
        assert np.all(result == 8)

    def test_clear(self) -> None:
        pipe = Pipeline()
        pipe.add(AddOnePlugin(), AddOneParams(value=1))
        pipe.clear()
        arr = np.ones((10, 10), dtype=np.int32)
        result = pipe.run(arr)
        assert np.all(result == 1)

    def test_step_count(self) -> None:
        pipe = Pipeline()
        assert len(pipe) == 0
        pipe.add(AddOnePlugin(), AddOneParams())
        assert len(pipe) == 1
