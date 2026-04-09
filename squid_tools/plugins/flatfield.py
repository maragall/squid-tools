from __future__ import annotations

import dask.array as da
import numpy as np
from pydantic import BaseModel

from squid_tools.core.data_model import Acquisition, OpticalMetadata
from squid_tools.plugins.base import ProcessingPlugin, TestCase


class FlatfieldParams(BaseModel):
    sigma: float = 16.0   # Gaussian smoothing sigma


class FlatfieldPlugin(ProcessingPlugin):
    name = "Flatfield Correction"
    category = "correction"
    requires_gpu = False

    def parameters(self) -> type[BaseModel]:
        return FlatfieldParams

    def validate(self, acq: Acquisition) -> list[str]:
        warnings = []
        total_fovs = sum(len(r.fovs) for r in acq.regions.values())
        if total_fovs < 4:
            warnings.append("Flatfield correction works best with >= 4 FOVs")
        return warnings

    def default_params(self, optical: OpticalMetadata) -> FlatfieldParams:
        return FlatfieldParams()

    def process(self, frames: da.Array, params: BaseModel) -> da.Array:
        assert isinstance(params, FlatfieldParams)
        return frames.map_blocks(_estimate_and_correct_flatfield, dtype=np.float64)

    def test_cases(self) -> list[TestCase]:
        return [
            TestCase(
                name="non_uniform_illumination",
                input_shape=(1, 1, 1, 64, 64),
                input_dtype="float64",
                description="Sinusoidal illumination pattern",
            )
        ]


def _estimate_and_correct_flatfield(block: np.ndarray) -> np.ndarray:
    from scipy.ndimage import gaussian_filter

    result = np.empty_like(block, dtype=np.float64)
    for idx in np.ndindex(block.shape[:-2]):
        frame = block[idx].astype(np.float64)
        flatfield = gaussian_filter(frame, sigma=min(frame.shape) // 4)
        flatfield_norm = (
            flatfield / flatfield.mean() if flatfield.mean() > 0 else np.ones_like(flatfield)
        )
        flatfield_norm = np.where(flatfield_norm > 0.1, flatfield_norm, 1.0)
        result[idx] = frame / flatfield_norm
    return result
