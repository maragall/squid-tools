"""Flatfield correction plugin.

Corrects illumination non-uniformity by dividing by a flatfield profile.
If no flatfield is provided, uses the image's own smoothed version as estimate.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from squid_tools.core.data_model import Acquisition, OpticalMetadata
from squid_tools.processing.base import ProcessingPlugin

logger = logging.getLogger(__name__)


class FlatfieldParams(BaseModel):
    """Parameters for flatfield correction."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    flatfield: np.ndarray | None = None
    smoothing_sigma: float = 50.0


class FlatfieldPlugin(ProcessingPlugin):
    """Flatfield illumination correction."""

    name = "Flatfield (BaSiC)"
    category = "shading"
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

    def run_live(self, selection, engine, params, progress):
        """Calibrate flatfield from samples, then install as per-tile transform."""
        import random

        # Phase 1: Calibrate
        candidates = selection if selection else engine.all_fov_indices()
        if not candidates:
            progress("Calibrating", 0, 1)
            progress("Applying", 1, 1)
            return

        n_samples = min(20, len(candidates))
        sample_indices = random.sample(sorted(candidates), n_samples)
        logger.info("Flatfield: calibrating from %d tiles", n_samples)
        progress("Calibrating", 0, n_samples)

        tiles = []
        for i, fov in enumerate(sample_indices):
            tiles.append(
                engine.get_raw_frame(fov, z=0, channel=0, timepoint=0)
            )
            progress("Calibrating", i + 1, n_samples)

        # Compute flatfield via the existing correction code (calculate_flatfield)
        from squid_tools.processing.flatfield.correction import calculate_flatfield
        flatfield, _darkfield = calculate_flatfield(tiles)

        # Phase 2: Apply — install a per-tile transform into the engine pipeline
        logger.info("Flatfield: applying correction to %d tiles", len(candidates))
        progress("Applying", 0, 1)

        def _flatfield_transform(frame):
            from squid_tools.processing.flatfield.correction import apply_flatfield
            return apply_flatfield(frame, flatfield)

        # Merge with any existing transforms (keep others)
        existing = list(engine._pipeline)
        # Avoid duplicating: drop any previous flatfield transform tagged via attribute
        existing = [t for t in existing if not getattr(t, "_is_flatfield", False)]
        _flatfield_transform._is_flatfield = True  # type: ignore[attr-defined]
        existing.append(_flatfield_transform)
        engine.set_pipeline(existing)

        progress("Applying", 1, 1)

    def test_cases(self) -> list[dict[str, Any]]:
        y, x = np.mgrid[0:128, 0:128]
        shading = 1.0 - 0.3 * ((x - 64) ** 2 + (y - 64) ** 2) / (64**2)
        frame = (1000 * shading).astype(np.float64)
        return [{"input": frame, "flatfield": shading, "description": "vignetting correction"}]
