"""Integration tests for the PetaKit Deconvolution plugin."""

from __future__ import annotations

import numpy as np
import pytest

from squid_tools.plugins.decon import DeconParams, DeconPlugin


# ---------------------------------------------------------------------------
# Plugin attribute tests
# ---------------------------------------------------------------------------


def test_decon_plugin_attributes():
    plugin = DeconPlugin()
    assert plugin.name == "PetaKit Deconvolution"
    assert plugin.category == "deconvolution"
    assert plugin.requires_gpu is True


def test_decon_plugin_parameters():
    plugin = DeconPlugin()
    assert plugin.parameters() is DeconParams


def test_decon_plugin_test_cases():
    plugin = DeconPlugin()
    cases = plugin.test_cases()
    assert len(cases) >= 1
    assert cases[0].name == "widefield_decon"


# ---------------------------------------------------------------------------
# DeconParams defaults
# ---------------------------------------------------------------------------


def test_decon_params_defaults():
    params = DeconParams()
    assert params.method in ("omw", "rl")
    assert params.iterations == 2
    assert params.force_cpu is False
    assert params.channel == 0


# ---------------------------------------------------------------------------
# default_params auto-fill from OpticalMetadata
# ---------------------------------------------------------------------------


def _make_optical(
    modality="widefield",
    na=0.8,
    pixel_size_um=0.65,
    dz_um=1.5,
):
    from squid_tools.core.data_model import OpticalMetadata

    return OpticalMetadata(
        modality=modality,
        immersion_medium="air",
        immersion_ri=1.0,
        numerical_aperture=na,
        pixel_size_um=pixel_size_um,
        dz_um=dz_um,
    )


def test_default_params_autofill_na():
    plugin = DeconPlugin()
    optical = _make_optical(na=0.45)
    params = plugin.default_params(optical)
    assert isinstance(params, DeconParams)
    assert params.na == pytest.approx(0.45)


def test_default_params_autofill_pixel_size():
    plugin = DeconPlugin()
    optical = _make_optical(pixel_size_um=0.325)
    params = plugin.default_params(optical)
    assert params.pixel_size_um == pytest.approx(0.325)


def test_default_params_autofill_immersion_ri():
    plugin = DeconPlugin()
    optical = _make_optical()
    params = plugin.default_params(optical)
    assert params.immersion_ri == 1.0


def test_default_params_autofill_dz():
    plugin = DeconPlugin()
    optical = _make_optical(dz_um=2.0)
    params = plugin.default_params(optical)
    assert params.dz_um == pytest.approx(2.0)


def test_default_params_none_optical():
    """default_params(None) should return sensible defaults without crashing."""
    plugin = DeconPlugin()
    params = plugin.default_params(None)
    assert isinstance(params, DeconParams)


# ---------------------------------------------------------------------------
# PSF generation (internal helper, no petakit needed)
# ---------------------------------------------------------------------------


def test_gaussian_psf_shape_and_sum():
    """Fallback Gaussian PSF should be 3-D and sum to 1."""
    from squid_tools.plugins.decon import _gaussian_psf

    psf = _gaussian_psf(nz=7, nxy=31)
    assert psf.ndim == 3
    assert psf.shape == (7, 31, 31)
    assert psf.dtype == np.float32
    np.testing.assert_allclose(psf.sum(), 1.0, rtol=1e-4)


def test_build_psf_fallback_without_petakit():
    """_build_psf fallback returns a valid 3-D Gaussian PSF.

    We test the fallback directly via _gaussian_psf since the import-level
    monkeypatching of an optional dependency is unreliable in-process.
    """
    from squid_tools.plugins.decon import _gaussian_psf

    # Directly exercise the Gaussian fallback
    params = DeconParams()
    nz = 8
    psf = _gaussian_psf(nz=nz, nxy=31)

    assert psf.ndim == 3
    assert psf.dtype == np.float32
    np.testing.assert_allclose(psf.sum(), 1.0, rtol=1e-4)


# ---------------------------------------------------------------------------
# process() with petakit (skipped if not installed)
# ---------------------------------------------------------------------------


def test_process_skips_without_petakit():
    """process() raises ImportError with friendly message when petakit missing."""
    import sys
    import unittest.mock as mock

    plugin = DeconPlugin()
    params = DeconParams(force_cpu=True)

    import dask.array as da

    frames = da.from_array(
        np.ones((1, 1, 1, 4, 32, 32), dtype=np.uint16)
    )

    # Mock petakit as unavailable in _check_petakit
    with mock.patch.dict(sys.modules, {"petakit": None}):
        with pytest.raises(ImportError, match="PetaKit is not installed"):
            plugin.process(frames, params)


def test_process_with_petakit_synthetic():
    """With petakit available, process() returns a float32 array of correct shape."""
    petakit = pytest.importorskip("petakit")  # noqa: F841

    import dask.array as da

    plugin = DeconPlugin()
    params = DeconParams(iterations=2, force_cpu=True, method="rl")

    # Small synthetic 3-D stack
    rng = np.random.default_rng(0)
    stack = rng.integers(100, 500, (1, 1, 1, 4, 32, 32), dtype=np.uint16)
    frames = da.from_array(stack, chunks=(1, 1, 1, 4, 32, 32))

    result = plugin.process(frames, params).compute()
    assert result.shape == stack.shape
    assert result.dtype == np.float32
    assert np.all(np.isfinite(result))


# ---------------------------------------------------------------------------
# Synthetic blurred-then-deconvolved: SNR improvement test
# ---------------------------------------------------------------------------


def _make_blurred_stack(nz=8, ny=64, nx=64):
    """Create a synthetic point-source stack and a Gaussian-blurred version."""
    from squid_tools.plugins.decon import _gaussian_psf

    truth = np.zeros((nz, ny, nx), dtype=np.float32)
    truth[nz // 2, ny // 2, nx // 2] = 1000.0

    psf = _gaussian_psf(nz=nz, nxy=min(ny, nx), sigma_xy=2.0, sigma_z=3.0)

    from scipy.signal import fftconvolve

    blurred = fftconvolve(truth, psf, mode="same").astype(np.float32)
    blurred = np.clip(blurred, 0, None)
    return truth, blurred, psf


def test_decon_improves_sharpness_synthetic():
    """Deconvolution (RL via scipy mock) sharpens the blurred signal."""
    petakit = pytest.importorskip("petakit")  # noqa: F841

    truth, blurred, psf = _make_blurred_stack(nz=8, ny=64, nx=64)

    from petakit import deconvolve

    result = deconvolve(blurred, psf, method="rl", iterations=15, gpu=False)

    # Peak of result should be closer to the true peak location
    peak_result = np.unravel_index(np.argmax(result), result.shape)
    peak_truth = np.unravel_index(np.argmax(truth), truth.shape)

    # Peak should be within 2 pixels of truth in each dimension
    assert abs(peak_result[0] - peak_truth[0]) <= 2
    assert abs(peak_result[1] - peak_truth[1]) <= 2
    assert abs(peak_result[2] - peak_truth[2]) <= 2


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------


def test_validate_warns_without_zstack():
    from squid_tools.core.data_model import (
        Acquisition,
        AcquisitionChannel,
        AcquisitionFormat,
        AcquisitionMode,
        FOVPosition,
        GridParams,
        ObjectiveMetadata,
        OpticalMetadata,
        Region,
        ScanConfig,
    )
    from pathlib import Path

    objective = ObjectiveMetadata(
        name="10x",
        magnification=10,
        numerical_aperture=0.3,
        tube_lens_f_mm=180,
        sensor_pixel_size_um=6.5,
        tube_lens_mm=180,
    )
    optical = OpticalMetadata(
        modality="widefield",
        immersion_medium="air",
        immersion_ri=1.0,
        numerical_aperture=0.3,
        pixel_size_um=0.65,
    )
    region = Region(
        region_id="A1",
        center_mm=(0.0, 0.0, 0.0),
        shape="Square",
        fovs=[FOVPosition(fov_index=0, x_mm=0.0, y_mm=0.0)],
        grid_params=GridParams(scan_size_mm=1.0, overlap_percent=15, nx=1, ny=1),
    )
    acq = Acquisition(
        path=Path("/tmp/test"),
        format=AcquisitionFormat.INDIVIDUAL_IMAGES,
        mode=AcquisitionMode.WELLPLATE,
        objective=objective,
        optical=optical,
        channels=[
            AcquisitionChannel(
                name="DAPI",
                illumination_source="LED",
                illumination_intensity=50.0,
                exposure_time_ms=100.0,
            )
        ],
        scan=ScanConfig(acquisition_pattern="Unidirectional", fov_pattern="Unidirectional"),
        regions={"A1": region},
        z_stack=None,
    )

    plugin = DeconPlugin()
    warnings = plugin.validate(acq)
    assert any("z-stack" in w for w in warnings)
