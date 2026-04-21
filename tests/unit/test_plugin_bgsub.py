"""Tests for BackgroundSubtractPlugin."""

from __future__ import annotations

import numpy as np
import pytest

sep = pytest.importorskip("sep")

from squid_tools.processing.bgsub.plugin import (  # noqa: E402
    BackgroundSubtractParams,
    BackgroundSubtractPlugin,
)


class TestBackgroundSubtractPlugin:
    def test_name(self) -> None:
        assert BackgroundSubtractPlugin().name == "Background Subtract"

    def test_default_params(self) -> None:
        params = BackgroundSubtractPlugin().default_params(None)
        assert isinstance(params, BackgroundSubtractParams)
        assert params.box_size == 64
        assert params.filter_size == 3

    def test_process_subtracts_uniform_bg(self) -> None:
        plugin = BackgroundSubtractPlugin()
        frame = np.full((128, 128), 500.0, dtype=np.float32)
        frame[64, 64] = 5000.0
        out = plugin.process(frame, BackgroundSubtractParams())
        # Uniform background should subtract to near-zero on most pixels
        assert np.median(out) < 10.0
        # Signal pixel is still bright (approximately 5000 - 500)
        assert out[64, 64] > 3000.0

    def test_process_rejects_non_2d(self) -> None:
        plugin = BackgroundSubtractPlugin()
        with pytest.raises(ValueError, match="2D"):
            plugin.process(
                np.zeros((2, 4, 4), dtype=np.float32),
                BackgroundSubtractParams(),
            )

    def test_manifest_loads(self) -> None:
        from squid_tools.core.gui_manifest import load_manifest
        from squid_tools.processing.bgsub import plugin as bgsub_plugin

        manifest = load_manifest(bgsub_plugin.__file__)
        assert manifest is not None
        assert manifest.name == "Background Subtract"
        assert manifest.parameters["box_size"].default == 64
