"""Background subtraction plugin using sep.Background.

sep (Source Extractor Python) builds a low-order polynomial + mesh
estimate of the sky/background and subtracts it. Classic fluorescence
microscopy uses the same trick to remove out-of-focus haze.

Source repo: https://github.com/sep-developers/sep (PyPI: sep)
Source GUI:  none (library, not an app). Manifest captured from
             sep.Background's docstring / typical param ranges.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from squid_tools.core.data_model import Acquisition, OpticalMetadata
from squid_tools.processing.base import ProcessingPlugin

logger = logging.getLogger(__name__)


class BackgroundSubtractParams(BaseModel):
    """Parameters forwarded to sep.Background."""

    box_size: int = Field(default=64)
    filter_size: int = Field(default=3)


class BackgroundSubtractPlugin(ProcessingPlugin):
    """Per-tile background subtraction (sep.Background)."""

    name: str = "Background Subtract"
    category: str = "correction"
    requires_gpu: bool = False

    def parameters(self) -> type[BaseModel]:
        return BackgroundSubtractParams

    def validate(self, acq: Acquisition) -> list[str]:
        try:
            import sep  # noqa: F401
        except ImportError:
            return ["sep not installed. `pip install sep` to enable."]
        return []

    def default_params(
        self, optical: OpticalMetadata | None = None,
    ) -> BaseModel:
        return BackgroundSubtractParams()

    def process(
        self, frame: np.ndarray, params: BaseModel,
    ) -> np.ndarray:
        """Estimate + subtract background; clip negatives to zero."""
        import sep

        p = params if isinstance(params, BackgroundSubtractParams) else BackgroundSubtractParams(
            **params.model_dump(),
        )
        if frame.ndim != 2:
            raise ValueError(f"frame must be 2D, got shape {frame.shape}")
        data = np.ascontiguousarray(frame.astype(np.float32))
        bg = sep.Background(data, bw=p.box_size, bh=p.box_size, fw=p.filter_size, fh=p.filter_size)
        bg_map = bg.back()
        out = data - bg_map
        np.clip(out, 0.0, None, out=out)
        return out.astype(np.float32)

    def test_cases(self) -> list[dict[str, Any]]:
        # A uniform image plus a tiny signal should subtract to near-zero
        # background (plus the signal preserved).
        base = np.full((128, 128), 500.0, dtype=np.float32)
        base[64, 64] = 5000.0
        return [
            {
                "name": "uniform_bg_subtracted",
                "input": base,
                "params": {"box_size": 64, "filter_size": 3},
            },
        ]
