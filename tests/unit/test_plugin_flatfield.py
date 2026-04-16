"""Tests for flatfield correction plugin."""

import numpy as np

from squid_tools.core.data_model import (
    OpticalMetadata,
)
from squid_tools.processing.flatfield.correction import apply_flatfield, calculate_flatfield_simple
from squid_tools.processing.flatfield.plugin import FlatfieldParams, FlatfieldPlugin


class TestFlatfieldPlugin:
    def test_instantiate(self) -> None:
        plugin = FlatfieldPlugin()
        assert plugin.name == "Flatfield Correction"
        assert plugin.category == "correction"

    def test_parameters(self) -> None:
        plugin = FlatfieldPlugin()
        assert plugin.parameters() is FlatfieldParams

    def test_process_corrects_shading(self) -> None:
        plugin = FlatfieldPlugin()
        # Create image with vignetting (brighter center, darker edges)
        y, x = np.mgrid[0:128, 0:128]
        shading = 1.0 - 0.3 * ((x - 64) ** 2 + (y - 64) ** 2) / (64**2)
        frame = (1000 * shading).astype(np.float64)
        # Provide the flatfield profile directly
        params = FlatfieldParams(flatfield=shading)
        result = plugin.process(frame, params)
        # After correction, variation should be reduced
        corrected_std = np.std(result)
        original_std = np.std(frame)
        assert corrected_std < original_std

    def test_default_params(self) -> None:
        plugin = FlatfieldPlugin()
        params = plugin.default_params(OpticalMetadata())
        assert isinstance(params, FlatfieldParams)

    def test_test_cases(self) -> None:
        plugin = FlatfieldPlugin()
        assert len(plugin.test_cases()) > 0


class TestFlatfieldCorrection:
    def test_apply_flatfield(self) -> None:
        # Create a non-uniform flatfield: center bright, edges dim
        y, x = np.mgrid[0:64, 0:64]
        flatfield = (0.5 + 0.5 * np.exp(-((x - 32) ** 2 + (y - 32) ** 2) / 200)).astype(np.float32)
        frame = np.full((64, 64), 1000.0, dtype=np.float32)
        result = apply_flatfield(frame, flatfield)
        # After correction, edges (low flatfield) should become brighter than center
        assert result[0, 0] > result[32, 32]

    def test_calculate_flatfield_simple(self) -> None:
        # Create tiles with vignetting pattern
        y, x = np.mgrid[0:64, 0:64]
        shading = 1.0 - 0.3 * ((x - 32) ** 2 + (y - 32) ** 2) / (32**2)
        tiles = [(1000 * shading).astype(np.float32) for _ in range(5)]
        flat = calculate_flatfield_simple(tiles)
        assert flat.shape == (64, 64)
        # Center should be brighter than edges in flatfield
        assert flat[32, 32] > flat[0, 0]
