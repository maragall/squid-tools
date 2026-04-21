"""Tests for Volume3DCanvas."""

from __future__ import annotations

import numpy as np
import pytest

from squid_tools.viewer.volume_canvas import Volume3DCanvas


def _synthetic_volume(z: int = 8, h: int = 16, w: int = 16) -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.random((z, h, w), dtype=np.float32)


class TestVolume3DCanvas:
    def test_instantiate(self, qtbot) -> None:
        canvas = Volume3DCanvas()
        try:
            assert canvas.native_widget() is not None
        finally:
            canvas.close()

    def test_set_volume_scalar(self, qtbot) -> None:
        canvas = Volume3DCanvas()
        try:
            canvas.set_volume(
                _synthetic_volume(),
                voxel_size_um=(0.325, 0.325, 5.0),
            )
            assert len(canvas._volume_visuals) == 1
        finally:
            canvas.close()

    def test_set_volume_rejects_2d(self, qtbot) -> None:
        canvas = Volume3DCanvas()
        try:
            bad = np.zeros((16, 16), dtype=np.float32)
            with pytest.raises(ValueError, match=r"\(Z, Y, X\)"):
                canvas.set_volume(bad, voxel_size_um=(1.0, 1.0, 1.0))
        finally:
            canvas.close()

    def test_set_volume_twice_replaces_visual(self, qtbot) -> None:
        canvas = Volume3DCanvas()
        try:
            canvas.set_volume(
                _synthetic_volume(z=4),
                voxel_size_um=(1.0, 1.0, 1.0),
            )
            first = canvas._volume_visuals[0]
            canvas.set_volume(
                _synthetic_volume(z=6),
                voxel_size_um=(1.0, 1.0, 1.0),
            )
            assert len(canvas._volume_visuals) == 1
            assert canvas._volume_visuals[0] is not first
        finally:
            canvas.close()

    def test_set_channel_volumes_two(self, qtbot) -> None:
        canvas = Volume3DCanvas()
        try:
            canvas.set_channel_volumes(
                volumes=[_synthetic_volume(), _synthetic_volume()],
                clims=[(0.0, 1.0), (0.0, 1.0)],
                cmaps=["reds", "greens"],
                voxel_size_um=(1.0, 1.0, 5.0),
            )
            assert len(canvas._volume_visuals) == 2
        finally:
            canvas.close()

    def test_set_channel_volumes_empty_raises(self, qtbot) -> None:
        canvas = Volume3DCanvas()
        try:
            with pytest.raises(ValueError, match="at least one"):
                canvas.set_channel_volumes(
                    volumes=[], clims=[], cmaps=[],
                    voxel_size_um=(1.0, 1.0, 1.0),
                )
        finally:
            canvas.close()

    def test_set_channel_volumes_length_mismatch_raises(self, qtbot) -> None:
        canvas = Volume3DCanvas()
        try:
            vol = _synthetic_volume()
            with pytest.raises(ValueError, match="same length"):
                canvas.set_channel_volumes(
                    volumes=[vol, vol], clims=[(0.0, 1.0)],
                    cmaps=["reds", "greens"],
                    voxel_size_um=(1.0, 1.0, 1.0),
                )
        finally:
            canvas.close()

    def test_set_channel_volumes_shape_mismatch_raises(self, qtbot) -> None:
        canvas = Volume3DCanvas()
        try:
            a = _synthetic_volume(z=4)
            b = _synthetic_volume(z=6)
            with pytest.raises(ValueError, match="same shape"):
                canvas.set_channel_volumes(
                    volumes=[a, b],
                    clims=[(0.0, 1.0), (0.0, 1.0)],
                    cmaps=["reds", "greens"],
                    voxel_size_um=(1.0, 1.0, 1.0),
                )
        finally:
            canvas.close()

    def test_close_idempotent(self, qtbot) -> None:
        canvas = Volume3DCanvas()
        canvas.close()
        canvas.close()


class TestVolume3DCanvasWithEngineVolume:
    def test_engine_single_channel_volume_displayed(
        self, qtbot, individual_acquisition,
    ) -> None:
        """End-to-end: engine Z-stack → Volume3DCanvas.set_volume."""
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")

        vol = engine.get_volume(fov=0, channel=0, timepoint=0)
        assert vol.ndim == 3
        canvas = Volume3DCanvas()
        try:
            canvas.set_volume(
                vol,
                voxel_size_um=engine.voxel_size_um(),
                clim=(0.0, 255.0),
                cmap="grays",
            )
        finally:
            canvas.close()

    def test_engine_multichannel_volume_displayed(
        self, qtbot, individual_acquisition,
    ) -> None:
        """End-to-end multi-channel: engine volumes → set_channel_volumes."""
        from squid_tools.viewer.viewport_engine import ViewportEngine

        engine = ViewportEngine()
        engine.load(individual_acquisition, "0")

        nc = len(engine._acquisition.channels)
        vols = [
            engine.get_volume(fov=0, channel=c, timepoint=0) for c in range(nc)
        ]
        clims = [(0.0, 255.0)] * nc
        cmaps = ["reds", "greens", "blues", "hot"][:nc]
        canvas = Volume3DCanvas()
        try:
            canvas.set_channel_volumes(
                vols, clims, cmaps, voxel_size_um=engine.voxel_size_um(),
            )
            assert len(canvas._volume_visuals) == nc
        finally:
            canvas.close()
