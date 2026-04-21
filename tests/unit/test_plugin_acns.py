"""Tests for ACNSPlugin."""

from __future__ import annotations

import numpy as np

from squid_tools.processing.acns.plugin import ACNSParams, ACNSPlugin


class TestACNSPlugin:
    def test_name_category(self) -> None:
        plugin = ACNSPlugin()
        assert plugin.name == "aCNS"
        assert plugin.category == "denoising"

    def test_default_params(self) -> None:
        params = ACNSPlugin().default_params(None)
        assert isinstance(params, ACNSParams)
        assert params.threshold_sigma == 3.0
        assert params.bias_value == 100.0

    def test_process_suppresses_noise_floor(self) -> None:
        plugin = ACNSPlugin()
        frame = np.full((4, 4), 102.0, dtype=np.float32)
        frame[2, 2] = 500.0
        out = plugin.process(frame, ACNSParams())
        # Background pixels are at bias+2 (below threshold 3*2.5=7.5) → zero
        assert out[0, 0] == 0.0
        # Signal pixel is above threshold → preserved (minus bias and threshold)
        assert out[2, 2] > 0.0

    def test_process_rejects_non_2d(self) -> None:
        import pytest

        plugin = ACNSPlugin()
        with pytest.raises(ValueError, match="2D"):
            plugin.process(np.zeros((2, 4, 4), dtype=np.float32), ACNSParams())

    def test_manifest_loads(self) -> None:
        from squid_tools.core.gui_manifest import load_manifest
        from squid_tools.processing.acns import plugin as acns_plugin

        manifest = load_manifest(acns_plugin.__file__)
        assert manifest is not None
        assert manifest.name == "aCNS"
        assert manifest.parameters["threshold_sigma"].default == 3.0
