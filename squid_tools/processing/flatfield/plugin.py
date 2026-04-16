"""Flatfield correction plugin.

Corrects illumination non-uniformity by dividing by a flatfield profile.
If no flatfield is provided, uses the image's own smoothed version as estimate.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from squid_tools.core.data_model import Acquisition, OpticalMetadata
from squid_tools.processing.base import ProcessingPlugin


class FlatfieldParams(BaseModel):
    """Parameters for flatfield correction."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    flatfield: np.ndarray | None = None
    smoothing_sigma: float = 50.0


class FlatfieldPlugin(ProcessingPlugin):
    """Flatfield illumination correction."""

    name = "Flatfield Correction"
    category = "correction"
    requires_gpu = False

    def parameters(self) -> type[BaseModel]:
        return FlatfieldParams

    def validate(self, acq: Acquisition) -> list[str]:
        return []

    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        assert isinstance(params, FlatfieldParams)
        from squid_tools.processing.flatfield.correction import apply_flatfield

        if params.flatfield is not None:
            return apply_flatfield(frames, params.flatfield)

        # Estimate from the image itself
        from scipy.ndimage import gaussian_filter

        flat = gaussian_filter(frames.astype(np.float32), sigma=params.smoothing_sigma)
        return apply_flatfield(frames, flat)

    def default_params(self, optical: OpticalMetadata | None = None) -> BaseModel:
        return FlatfieldParams()

    def test_cases(self) -> list[dict[str, Any]]:
        y, x = np.mgrid[0:128, 0:128]
        shading = 1.0 - 0.3 * ((x - 64) ** 2 + (y - 64) ** 2) / (64**2)
        frame = (1000 * shading).astype(np.float64)
        return [{"input": frame, "flatfield": shading, "description": "vignetting correction"}]
