"""PetaKit Deconvolution plugin for squid-tools.

Wraps the PetaKit library (Richardson-Lucy + OMW deconvolution).
PetaKit is an optional dependency; if not installed, a clear ImportError
with install instructions is raised at call time.
"""

from __future__ import annotations

import dask.array as da
import numpy as np
from pydantic import BaseModel

from squid_tools.core.data_model import Acquisition, OpticalMetadata
from squid_tools.plugins.base import ProcessingPlugin, TestCase


class DeconParams(BaseModel):
    modality: str = "widefield"
    iterations: int = 10
    regularization: float = 0.001
    method: str = "omw"       # "omw" (fast) or "rl" (high resolution)
    use_gpu: bool = True       # GPU-first; CPU fallback
    # PSF parameters (auto-filled from OpticalMetadata when available)
    na: float = 0.8
    pixel_size_um: float = 0.65
    dz_um: float = 1.0
    emission_wavelength_um: float = 0.525
    immersion_ri: float = 1.0
    # PSF size (0 = auto)
    nz_psf: int = 0
    nxy_psf: int = 0


class DeconPlugin(ProcessingPlugin):
    """Per-frame deconvolution via PetaKit (GPU-first, CPU fallback)."""

    name = "PetaKit Deconvolution"
    category = "deconvolution"
    requires_gpu = True  # CuPy preferred; CPU fallback available

    def parameters(self) -> type[BaseModel]:
        return DeconParams

    def validate(self, acq: Acquisition) -> list[str]:
        warnings: list[str] = []
        if acq.z_stack is None:
            warnings.append(
                "Deconvolution works best with z-stacks; "
                "single-plane acquisitions will use a 2-D approximation"
            )
        return warnings

    def default_params(self, optical: OpticalMetadata) -> DeconParams:
        """Auto-fill PSF parameters from OpticalMetadata."""
        if optical is None:
            return DeconParams()

        # Estimate emission wavelength: use 0.525 µm (green) as default
        emission_um = 0.525

        # Infer immersion RI from NA
        try:
            from petakit.psf import infer_immersion_index

            ri = infer_immersion_index(optical.numerical_aperture)
        except ImportError:
            ri = optical.immersion_ri

        return DeconParams(
            modality=optical.modality,
            na=optical.numerical_aperture,
            pixel_size_um=optical.pixel_size_um,
            dz_um=optical.dz_um if optical.dz_um is not None else 1.0,
            emission_wavelength_um=emission_um,
            immersion_ri=ri,
        )

    def process(self, frames: da.Array, params: BaseModel) -> da.Array:
        """Apply deconvolution per z-stack block via map_blocks.

        The input ``frames`` is expected to have shape
        ``(regions, fovs, t, z, y, x)`` or a compatible broadcast shape.
        Deconvolution is applied to the (z, y, x) inner dimensions.

        If petakit is not installed an ImportError is raised with install
        instructions.
        """
        assert isinstance(params, DeconParams)

        # Validate petakit is available early so the error is immediate
        _check_petakit()

        psf = _build_psf(params, nz=frames.shape[-3] if frames.ndim >= 3 else 1)

        return frames.map_blocks(
            _deconvolve_block,
            dtype=np.float32,
            meta=np.empty(0, dtype=np.float32),
            psf=psf,
            params=params,
        )

    def test_cases(self) -> list[TestCase]:
        return [
            TestCase(
                name="widefield_decon",
                input_shape=(1, 1, 1, 16, 64, 64),
                input_dtype="uint16",
                description="Single FOV z-stack, widefield deconvolution",
            )
        ]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_petakit() -> None:
    """Raise a friendly ImportError if petakit is not available."""
    try:
        import petakit  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "PetaKit is not installed. "
            "Install it with: pip install petakit\n"
            "or: pip install 'squid-tools[decon]'"
        ) from exc


def _build_psf(params: DeconParams, nz: int = 1) -> np.ndarray:
    """Generate a theoretical PSF from DeconParams.

    Uses petakit.psf.generate_psf when available; otherwise falls back to
    a simple Gaussian approximation so tests without petakit still work.
    """
    try:
        from petakit.psf import compute_psf_size, generate_psf

        if params.nz_psf > 0 and params.nxy_psf > 0:
            nz_psf, nxy_psf = params.nz_psf, params.nxy_psf
        else:
            nz_psf, nxy_psf = compute_psf_size(
                nz_acquisition=max(nz, 1),
                dxy=params.pixel_size_um,
                dz=params.dz_um,
                wavelength=params.emission_wavelength_um,
                na=params.na,
                ni=params.immersion_ri,
            )

        return generate_psf(
            nz=nz_psf,
            nxy=nxy_psf,
            dxy=params.pixel_size_um,
            dz=params.dz_um,
            wavelength=params.emission_wavelength_um,
            na=params.na,
            ni=params.immersion_ri,
        )
    except ImportError:
        # Fallback: 3-D Gaussian PSF
        return _gaussian_psf(
            nz=max(nz, 3) if nz > 1 else 3,
            nxy=31,
            sigma_xy=2.0,
            sigma_z=4.0,
        )


def _gaussian_psf(
    nz: int = 7, nxy: int = 31, sigma_xy: float = 2.0, sigma_z: float = 4.0
) -> np.ndarray:
    """Simple 3-D Gaussian PSF for testing without psfmodels."""
    z = np.linspace(-(nz // 2), nz // 2, nz)
    y = np.linspace(-(nxy // 2), nxy // 2, nxy)
    x = np.linspace(-(nxy // 2), nxy // 2, nxy)
    ZZ, YY, XX = np.meshgrid(z, y, x, indexing="ij")
    psf = np.exp(-(XX**2 + YY**2) / (2 * sigma_xy**2) - ZZ**2 / (2 * sigma_z**2))
    psf /= psf.sum()
    return psf.astype(np.float32)


def _deconvolve_block(
    block: np.ndarray,
    psf: np.ndarray,
    params: DeconParams,
    block_info=None,
) -> np.ndarray:
    """Apply deconvolution to a single dask block.

    The block can have arbitrary leading dimensions; deconvolution is applied
    to the last three axes (z, y, x). For 2-D-only blocks (nz=1) a singleton
    z dimension is added temporarily.
    """
    try:
        from petakit import deconvolve
    except ImportError as exc:
        raise ImportError(
            "PetaKit is not installed. "
            "Install it with: pip install petakit\n"
            "or: pip install 'squid-tools[decon]'"
        ) from exc

    result = np.empty(block.shape, dtype=np.float32)
    # Iterate over all leading dims (regions, fovs, t) and deconvolve each z-stack
    spatial_ndim = 3
    leading_shape = block.shape[:-spatial_ndim]
    for idx in np.ndindex(leading_shape) if leading_shape else [()]:
        stack = block[idx].astype(np.float32)  # (Z, Y, X)
        if stack.ndim == 2:
            stack = stack[np.newaxis]  # add Z dim
            squeeze = True
        else:
            squeeze = False

        deconvolved = deconvolve(
            stack,
            psf,
            method=params.method,
            iterations=params.iterations,
            gpu=params.use_gpu,
        )

        if squeeze:
            deconvolved = deconvolved[0]

        result[idx] = deconvolved.astype(np.float32)

    return result
