from __future__ import annotations

import dask.array as da
import numpy as np
from pydantic import BaseModel

from squid_tools.core.data_model import Acquisition, OpticalMetadata
from squid_tools.plugins.base import ProcessingPlugin, TestCase


class BackgroundParams(BaseModel):
    box_size: int = 64
    filter_size: int = 3


class BackgroundPlugin(ProcessingPlugin):
    name = "Background Subtraction"
    category = "correction"
    requires_gpu = False

    def parameters(self) -> type[BaseModel]:
        return BackgroundParams

    def validate(self, acq: Acquisition) -> list[str]:
        return []

    def default_params(self, optical: OpticalMetadata) -> BackgroundParams:
        return BackgroundParams()

    def process(self, frames: da.Array, params: BaseModel) -> da.Array:
        assert isinstance(params, BackgroundParams)
        return frames.map_blocks(
            _subtract_background,
            dtype=frames.dtype,
            bw=params.box_size,
            fw=params.filter_size,
        )

    def test_cases(self) -> list[TestCase]:
        return [
            TestCase(
                name="uniform_background",
                input_shape=(1, 1, 1, 64, 64),
                input_dtype="float64",
                description="Uniform background with bright object",
            )
        ]


def _subtract_background(block: np.ndarray, bw: int = 64, fw: int = 3) -> np.ndarray:
    import sep

    result = np.empty_like(block)
    # Process each 2D frame
    for idx in np.ndindex(block.shape[:-2]):
        frame = block[idx].astype(np.float64, copy=True)
        frame = np.ascontiguousarray(frame)
        bkg = sep.Background(frame, bw=bw, bh=bw, fw=fw, fh=fw)
        result[idx] = frame - bkg.back()
    return result
