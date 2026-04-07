from __future__ import annotations

from abc import ABC, abstractmethod

import dask.array as da
from pydantic import BaseModel

from squid_tools.core.data_model import Acquisition, OpticalMetadata


class TestCase(BaseModel):
    name: str
    input_shape: tuple[int, ...]
    input_dtype: str = "uint16"
    description: str = ""


class ProcessingPlugin(ABC):
    name: str
    category: str
    requires_gpu: bool = False

    @abstractmethod
    def parameters(self) -> type[BaseModel]: ...

    @abstractmethod
    def validate(self, acq: Acquisition) -> list[str]: ...

    @abstractmethod
    def process(self, frames: da.Array, params: BaseModel) -> da.Array: ...

    @abstractmethod
    def default_params(self, optical: OpticalMetadata) -> BaseModel: ...

    @abstractmethod
    def test_cases(self) -> list[TestCase]: ...
