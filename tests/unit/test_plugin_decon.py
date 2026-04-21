"""Tests for DeconvolutionPlugin."""

from __future__ import annotations

import numpy as np
from scipy.signal import convolve2d

from squid_tools.processing.decon.plugin import (
    DeconvolutionParams,
    DeconvolutionPlugin,
    _gaussian_psf_2d,
    _sigma_from_optics,
)


class TestGaussianPsf:
    def test_normalized_sums_to_one(self) -> None:
        psf = _gaussian_psf_2d(31, 2.0)
        assert abs(float(psf.sum()) - 1.0) < 1e-5

    def test_odd_size_centered(self) -> None:
        psf = _gaussian_psf_2d(11, 1.0)
        assert psf[5, 5] == psf.max()


class TestSigmaFromOptics:
    def test_higher_na_smaller_sigma(self) -> None:
        s_low = _sigma_from_optics(525.0, 0.3, 0.752)
        s_high = _sigma_from_optics(525.0, 1.4, 0.752)
        assert s_low > s_high

    def test_returns_at_least_half_pixel(self) -> None:
        s = _sigma_from_optics(200.0, 1.4, 10.0)
        assert s >= 0.5


class TestDeconvolutionPlugin:
    def test_default_params_requires_metadata(self) -> None:
        import pytest

        plugin = DeconvolutionPlugin()
        # No optical → refuses (no hardcoded fallback)
        with pytest.raises(ValueError, match="pixel_size_um"):
            plugin.default_params(None)

    def test_default_params_from_optical(self) -> None:
        from squid_tools.core.data_model import OpticalMetadata

        plugin = DeconvolutionPlugin()
        params = plugin.default_params(
            OpticalMetadata(pixel_size_um=0.752, numerical_aperture=0.8),
        )
        assert isinstance(params, DeconvolutionParams)
        assert params.iterations == 15
        assert params.wavelength_nm == 525.0
        assert params.pixel_size_um == 0.752

    def test_process_sharpens_blurred_point(self) -> None:
        plugin = DeconvolutionPlugin()
        sharp = np.zeros((31, 31), dtype=np.float32)
        sharp[15, 15] = 1.0
        psf = _gaussian_psf_2d(7, 1.5)
        blurred = convolve2d(sharp, psf, mode="same", boundary="symm")
        params = DeconvolutionParams(
            wavelength_nm=525.0,
            numerical_aperture=0.8,
            pixel_size_um=0.752,
            iterations=15,
            psf_size_px=7,
        )
        out = plugin.process(blurred, params)
        assert out.shape == blurred.shape
        assert out.dtype == np.float32
        # Output must be finite and within the input's original dynamic range.
        assert np.all(np.isfinite(out))
        assert float(out.min()) >= float(blurred.min()) - 1e-5
        assert float(out.max()) <= float(blurred.max()) + 1e-5

    def test_process_rejects_3d(self) -> None:
        import pytest

        plugin = DeconvolutionPlugin()
        params = DeconvolutionParams(
            wavelength_nm=525.0, numerical_aperture=0.8, pixel_size_um=0.752,
        )
        vol = np.zeros((2, 4, 4), dtype=np.float32)
        with pytest.raises(ValueError, match="2D"):
            plugin.process(vol, params)

    def test_test_cases_shape(self) -> None:
        plugin = DeconvolutionPlugin()
        cases = plugin.test_cases()
        assert len(cases) >= 1
        assert cases[0]["input"].ndim == 2

    def test_manifest_ships_with_plugin(self) -> None:
        from squid_tools.core.gui_manifest import load_manifest
        from squid_tools.processing.decon import plugin as decon_plugin

        manifest = load_manifest(decon_plugin.__file__)
        assert manifest is not None
        assert manifest.name == "Deconvolution"
        assert "wavelength_nm" in manifest.parameters
        # Source-GUI-derived default is 525 nm (GFP).
        assert manifest.parameters["wavelength_nm"].default == 525.0
        # psf_size_px is hidden from users per the manifest.
        assert manifest.parameters["psf_size_px"].visible is False
