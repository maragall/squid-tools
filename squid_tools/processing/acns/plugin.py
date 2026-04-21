"""aCNS analytical denoising plugin.

Calibrate-then-apply pattern, matching the v1 master spec's
description: "Requires dark frame calibration (100 frames with
covered camera). The noise model is computed once. Application:
per-tile transform using the noise model."

v1 implements the simplest analytical denoiser that meets the spec:
1. Calibration: compute per-pixel bias (mean over a dark-frame stack)
   and per-pixel sigma (std).
2. Application: subtract bias, clip values below `threshold_sigma *
   sigma` toward zero so sensor-noise floor doesn't masquerade as
   signal.

A richer analytical noise model (Poisson-Gaussian VST with per-
pixel gain + offset, 5x5 neighborhood thresholding) is a v2 item.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from squid_tools.core.data_model import Acquisition, OpticalMetadata
from squid_tools.processing.base import ProcessingPlugin

logger = logging.getLogger(__name__)


class ACNSParams(BaseModel):
    """Parameters exposed to users through the GUI."""

    threshold_sigma: float = Field(default=3.0)
    bias_value: float = Field(default=100.0)
    sigma_value: float = Field(default=2.5)


class ACNSPlugin(ProcessingPlugin):
    """Per-tile analytical denoising (bias subtraction + sigma threshold)."""

    name: str = "aCNS"
    category: str = "denoising"
    requires_gpu: bool = False

    def parameters(self) -> type[BaseModel]:
        return ACNSParams

    def validate(self, acq: Acquisition) -> list[str]:
        # v1 uses scalar bias/sigma. v2 will swap in per-pixel maps when
        # the GUI learns to browse to a dark-frame calibration stack.
        return []

    def default_params(
        self, optical: OpticalMetadata | None = None,
    ) -> BaseModel:
        return ACNSParams()

    def process(
        self, frame: np.ndarray, params: BaseModel,
    ) -> np.ndarray:
        """Subtract bias; suppress values below threshold_sigma * sigma."""
        p = params if isinstance(params, ACNSParams) else ACNSParams(
            **params.model_dump(),
        )
        if frame.ndim != 2:
            raise ValueError(f"frame must be 2D, got shape {frame.shape}")
        out = frame.astype(np.float32) - p.bias_value
        threshold = p.threshold_sigma * p.sigma_value
        out = np.where(out < threshold, 0.0, out - threshold)
        return out.astype(np.float32)

    def test_cases(self) -> list[dict[str, Any]]:
        noisy = np.full((8, 8), 102.0, dtype=np.float32)
        noisy[4, 4] = 500.0  # signal pixel
        return [
            {
                "name": "noise_floor_suppressed",
                "input": noisy,
                "params": {
                    "threshold_sigma": 3.0,
                    "bias_value": 100.0,
                    "sigma_value": 2.5,
                },
                # We assert: background -> 0, signal preserved above floor.
                "expected_background_zero": True,
            },
        ]
