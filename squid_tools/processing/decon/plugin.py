"""Deconvolution plugin.

Richardson-Lucy (scikit-image) with a Gaussian PSF computed from the
objective's NA, pixel size, and channel wavelength. Absorbed from
Cephla-Lab/Deconvolution (petakit) with a simplified PSF generator —
v1 does per-tile 2D deconvolution; 3D volumetric decon is deferred
to v2 when we have psfmodels + CuPy bundled.

Source repo:  https://github.com/Cephla-Lab/Deconvolution
Source GUI:   src/petakit/gui/main.py (parameter manifest captured at
              processing/decon/gui_manifest.yaml)
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from squid_tools.core.data_model import Acquisition, OpticalMetadata
from squid_tools.processing.base import ProcessingPlugin

logger = logging.getLogger(__name__)


class DeconvolutionParams(BaseModel):
    """Parameters exposed to users through the GUI.

    See gui_manifest.yaml for which fields are visible, default values,
    and tooltips captured from the source petakit GUI.
    """

    wavelength_nm: float = Field(default=525.0)
    numerical_aperture: float = Field(default=0.8)
    pixel_size_um: float = Field(default=0.752)
    iterations: int = Field(default=15)
    psf_size_px: int = Field(default=31)


def _gaussian_psf_2d(size: int, sigma: float) -> np.ndarray:
    """Generate a centered, normalized 2D Gaussian PSF."""
    ax = np.arange(-(size // 2), size // 2 + 1, dtype=np.float32)
    xx, yy = np.meshgrid(ax, ax)
    psf = np.exp(-(xx * xx + yy * yy) / (2.0 * sigma * sigma))
    s = psf.sum()
    return (psf / s).astype(np.float32) if s > 0 else psf


def _sigma_from_optics(
    wavelength_nm: float, na: float, pixel_size_um: float,
) -> float:
    """Airy disk radius in pixels ≈ 0.61 * λ / NA. Sigma ≈ radius / 2.355."""
    radius_um = 0.61 * (wavelength_nm / 1000.0) / max(na, 0.01)
    radius_px = radius_um / max(pixel_size_um, 1e-6)
    sigma_px = max(radius_px / 2.355, 0.5)
    return float(sigma_px)


class DeconvolutionPlugin(ProcessingPlugin):
    """Per-tile 2D Richardson-Lucy deconvolution."""

    name: str = "Deconvolution"
    category: str = "deconvolution"
    requires_gpu: bool = False

    def parameters(self) -> type[BaseModel]:
        return DeconvolutionParams

    def validate(self, acq: Acquisition) -> list[str]:
        warnings: list[str] = []
        if acq.objective is None or acq.objective.pixel_size_um <= 0:
            warnings.append("Objective pixel size unknown; using default 0.752 µm.")
        return warnings

    def default_params(
        self, optical: OpticalMetadata | None = None,
    ) -> BaseModel:
        if optical is None:
            return DeconvolutionParams()
        kwargs: dict[str, Any] = {}
        if optical.pixel_size_um:
            kwargs["pixel_size_um"] = optical.pixel_size_um
        if optical.numerical_aperture:
            kwargs["numerical_aperture"] = float(optical.numerical_aperture)
        return DeconvolutionParams(**kwargs)

    def process(
        self, frame: np.ndarray, params: BaseModel,
    ) -> np.ndarray:
        """Richardson-Lucy deconvolution of a single 2D tile."""
        from skimage.restoration import richardson_lucy

        p = params if isinstance(params, DeconvolutionParams) else DeconvolutionParams(
            **params.model_dump(),
        )
        if frame.ndim != 2:
            raise ValueError(f"frame must be 2D, got shape {frame.shape}")
        sigma = _sigma_from_optics(
            p.wavelength_nm, p.numerical_aperture, p.pixel_size_um,
        )
        psf = _gaussian_psf_2d(p.psf_size_px, sigma)

        # scikit-image's richardson_lucy expects float images in [0, 1]
        f = frame.astype(np.float32)
        lo, hi = float(f.min()), float(f.max())
        if hi <= lo:
            return frame.astype(np.float32)
        normed = (f - lo) / (hi - lo)
        out = richardson_lucy(normed, psf, num_iter=p.iterations, clip=False)
        out = np.clip(out, 0.0, 1.0) * (hi - lo) + lo
        return out.astype(np.float32)

    def test_cases(self) -> list[dict[str, Any]]:
        """Synthetic test: a blurred pixel should sharpen toward the input."""
        sharp = np.zeros((31, 31), dtype=np.float32)
        sharp[15, 15] = 1.0
        # Blur with a small kernel to create an "acquired" frame.
        psf = _gaussian_psf_2d(7, 1.5)
        from scipy.signal import convolve2d
        blurred = convolve2d(sharp, psf, mode="same", boundary="symm")
        return [
            {
                "name": "point_source_sharpens",
                "input": blurred,
                "params": {
                    "wavelength_nm": 525.0,
                    "numerical_aperture": 0.8,
                    "pixel_size_um": 0.752,
                    "iterations": 15,
                    "psf_size_px": 7,
                },
                # We only assert the result is more peaked than the input;
                # exact values depend on RL convergence.
                "expected_peak_greater": True,
            },
        ]
