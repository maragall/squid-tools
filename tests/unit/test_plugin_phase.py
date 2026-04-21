"""Tests for PhaseFromDefocusPlugin (v1 stub)."""

from __future__ import annotations

import numpy as np

from squid_tools.processing.phase.plugin import (
    PhaseFromDefocusParams,
    PhaseFromDefocusPlugin,
)


class TestPhaseFromDefocusPlugin:
    def test_name_and_category(self) -> None:
        plugin = PhaseFromDefocusPlugin()
        assert plugin.name == "Phase from Defocus"
        assert plugin.category == "phase"

    def test_default_params(self) -> None:
        plugin = PhaseFromDefocusPlugin()
        params = plugin.default_params(None)
        assert isinstance(params, PhaseFromDefocusParams)
        assert params.wavelength_um == 0.520
        assert params.illumination_na_ratio == 0.87

    def test_process_is_stub_passthrough(self) -> None:
        plugin = PhaseFromDefocusPlugin()
        frame = np.random.default_rng(0).random((8, 8), dtype=np.float32)
        params = PhaseFromDefocusParams()
        out = plugin.process(frame, params)
        assert np.array_equal(out, frame)

    def test_manifest_loads(self) -> None:
        from squid_tools.core.gui_manifest import load_manifest
        from squid_tools.processing.phase import plugin as phase_plugin

        manifest = load_manifest(phase_plugin.__file__)
        assert manifest is not None
        assert manifest.name == "Phase from Defocus"
        assert manifest.parameters["illumination_na_ratio"].default == 0.87
        assert manifest.parameters["regularization_strength"].visible is False
