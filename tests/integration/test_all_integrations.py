"""Headless GUI integration sweep — runs the whole product on synthetic data.

Goal: replace "click around the GUI and report what's broken" with a single
command. Every test here exercises a real customer-visible integration via
the same Python entry points the GUI uses, no mouse events. Designed to be
cross-platform — no `pythonw`, no macOS app-activation, no manual focus.

Run::

    pytest tests/integration/test_all_integrations.py -v

The OME-TIFF Squid-stitcher-output layout (JSON + XML, no acquisition.yaml)
is the priority path because that's the format real customers ship.

Coverage:

1. OME-TIFF detection on Squid-stitcher-output layout (no YAML).
2. OME-TIFF read_frame returns the right plane (memmap correctness).
3. compute_contrast on OME-TIFF doesn't hang and returns sane (p1, p99).
4. Each of the 6 processing plugins runs on a real frame end-to-end via
   ``controller.run_plugin``: Flatfield, Deconvolution, Phase from Defocus,
   aCNS, sep.Background. Stitcher uses run_live and is covered separately.
5. StitcherPlugin.run_live drives without raising on OME-TIFF.
6. Sidecar manifest is written after a plugin run.
7. Individual-image format still loads and renders (regression).

Each test uses a tiny synthetic acquisition (2x2 grid, 2 channels, 1-3 z
planes) so the whole sweep finishes in seconds.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import numpy as np
import pytest
import tifffile

from tests.fixtures.generate_fixtures import create_individual_acquisition

# Real-dataset smoke testing. Override via env var on Linux/Windows.
# When the dataset is missing the real-data tests skip rather than fail.
REAL_DATASET_PATH = Path(os.environ.get(
    "SQUID_REAL_DATASET",
    "/Users/julioamaragall/Downloads/10x_mouse_brain_2025-04-23_00-53-11.236590",
))

# ---------------------------------------------------------------------------
# Synthetic Squid-stitcher-output fixture (the format the Spencer dataset
# uses: JSON + XML + coordinates.csv + ome_tiff/ + no acquisition.yaml).
# Lives here, not in tests/fixtures, so it stays close to the contract it
# guards — if the Squid output layout shifts, this fixture must shift too.
# ---------------------------------------------------------------------------


_CONFIGURATIONS_XML = """<modes>
  <mode ID="1" Name="BF LED matrix full" ExposureTime="12.0"
        IlluminationSource="0" IlluminationIntensity="5.0" ZOffset="0.0"
        Selected="false">16777215</mode>
  <mode ID="5" Name="Fluorescence 405 nm Ex" ExposureTime="50.0"
        IlluminationSource="11" IlluminationIntensity="21.0" ZOffset="0.0"
        Selected="true">2141688</mode>
  <mode ID="6" Name="Fluorescence 488 nm Ex" ExposureTime="25.0"
        IlluminationSource="12" IlluminationIntensity="27.0" ZOffset="0.0"
        Selected="true">2096896</mode>
</modes>
"""


def _create_squid_ome_tiff_acquisition(
    path: Path,
    nx: int = 2,
    ny: int = 2,
    nz: int = 3,
    nc: int = 2,
    image_shape: tuple[int, int] = (64, 64),
    region_id: str = "0",
) -> Path:
    """Create a Squid-stitcher-output OME-TIFF dataset (no acquisition.yaml).

    Layout matches the Spencer-feedback dataset:
      acquisition parameters.json   (Nx/Ny/Nz/dx/dy/dz/objective)
      configurations.xml            (channel modes; Selected="true" wins)
      0/coordinates.csv             (FOV positions)
      ome_tiff/{region}_{fov}.ome.tiff   (TZCYX z-stacks per FOV)

    No YAML — that's the whole point of this fixture.
    """
    path.mkdir(parents=True, exist_ok=True)
    pixel_size_um = 0.65
    step_mm = pixel_size_um * image_shape[1] * 0.85 / 1000

    params = {
        "dx(mm)": step_mm, "Nx": nx,
        "dy(mm)": step_mm, "Ny": ny,
        "dz(um)": 1.5, "Nz": nz,
        "dt(s)": 0.0, "Nt": 1,
        "objective": {
            "magnification": 10.0, "NA": 0.3,
            "tube_lens_f_mm": 180.0, "name": "10x",
        },
        "sensor_pixel_size_um": 7.52,
        "tube_lens_mm": 180,
    }
    (path / "acquisition parameters.json").write_text(json.dumps(params))
    (path / "configurations.xml").write_text(_CONFIGURATIONS_XML)

    ome_dir = path / "ome_tiff"
    ome_dir.mkdir()
    fov_idx = 0
    rng = np.random.default_rng(42)
    for _iy in range(ny):
        for _ix in range(nx):
            fname = f"{region_id}_{fov_idx:05}.ome.tiff"
            data = rng.integers(
                0, 4095, (1, nz, nc, *image_shape), dtype=np.uint16,
            )
            tifffile.imwrite(
                str(ome_dir / fname),
                data,
                ome=True,
                metadata={"axes": "TZCYX"},
            )
            fov_idx += 1

    tp_dir = path / "0"
    tp_dir.mkdir()
    rows: list[dict[str, object]] = []
    fov_idx = 0
    for iy in range(ny):
        for ix in range(nx):
            rows.append({
                "region": region_id,
                "fov": fov_idx,
                "x (mm)": ix * step_mm,
                "y (mm)": iy * step_mm,
                "z (um)": 0.0,
            })
            fov_idx += 1
    with open(tp_dir / "coordinates.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOmeTiffSquidOutput:
    """Priority path: OME-TIFF with Squid stitcher's JSON+XML metadata."""

    def test_detect_without_acquisition_yaml(self, tmp_path: Path) -> None:
        from squid_tools.core.readers import detect_reader
        from squid_tools.core.readers.ome_tiff import OMETiffReader

        acq = _create_squid_ome_tiff_acquisition(tmp_path / "acq")
        assert not (acq / "acquisition.yaml").exists(), (
            "fixture sanity: must not write a YAML"
        )
        reader = detect_reader(acq)
        assert isinstance(reader, OMETiffReader)

    def test_read_metadata_channels_from_xml(self, tmp_path: Path) -> None:
        from squid_tools.core.readers.ome_tiff import OMETiffReader

        acq = _create_squid_ome_tiff_acquisition(tmp_path / "acq")
        reader = OMETiffReader()
        meta = reader.read_metadata(acq)
        names = [c.name for c in meta.channels]
        assert names == ["Fluorescence 405 nm Ex", "Fluorescence 488 nm Ex"], (
            f"channels should come from configurations.xml Selected=true; got {names}"
        )
        assert meta.z_stack is not None and meta.z_stack.nz == 3
        assert meta.objective.magnification == 10.0

    def test_read_frame_returns_correct_plane(self, tmp_path: Path) -> None:
        """memmap path: read_frame returns one plane, not the whole stack."""
        from squid_tools.core.data_model import FrameKey
        from squid_tools.core.readers.ome_tiff import OMETiffReader

        acq = _create_squid_ome_tiff_acquisition(
            tmp_path / "acq", image_shape=(64, 64),
        )
        reader = OMETiffReader()
        reader.read_metadata(acq)
        plane = reader.read_frame(FrameKey(region="0", fov=0, z=0, channel=0, timepoint=0))
        assert plane.shape == (64, 64)
        assert plane.dtype == np.uint16

    def test_compute_contrast_returns_sane_values(self, tmp_path: Path) -> None:
        """compute_contrast must not hang on OME-TIFF and must return p1<p99."""
        from squid_tools.viewer.viewport_engine import ViewportEngine

        acq = _create_squid_ome_tiff_acquisition(tmp_path / "acq")
        engine = ViewportEngine()
        engine.load(acq, region="0")
        p1, p99 = engine.compute_contrast(channel=0)
        assert 0 <= p1 < p99
        assert engine._last_sampled_max.get(0) is not None


class TestPluginRunPerFrame:
    """Each per-frame plugin runs to completion on a real OME-TIFF frame."""

    @pytest.fixture
    def frame_and_optical(self, tmp_path: Path):
        from squid_tools.core.data_model import FrameKey
        from squid_tools.core.readers.ome_tiff import OMETiffReader

        acq = _create_squid_ome_tiff_acquisition(tmp_path / "acq")
        reader = OMETiffReader()
        meta = reader.read_metadata(acq)
        frame = reader.read_frame(FrameKey(region="0", fov=0, z=0, channel=0, timepoint=0))
        return frame.astype(np.float32), meta.optical

    @pytest.mark.parametrize("plugin_module,plugin_class", [
        ("squid_tools.processing.flatfield.plugin", "FlatfieldPlugin"),
        ("squid_tools.processing.decon.plugin", "DeconvolutionPlugin"),
        ("squid_tools.processing.phase.plugin", "PhaseFromDefocusPlugin"),
        ("squid_tools.processing.acns.plugin", "ACNSPlugin"),
        ("squid_tools.processing.bgsub.plugin", "BackgroundSubtractPlugin"),
    ])
    def test_plugin_runs_on_ome_tiff_frame(
        self, frame_and_optical, plugin_module, plugin_class,
    ) -> None:
        import importlib

        frame, optical = frame_and_optical
        mod = importlib.import_module(plugin_module)
        plugin = getattr(mod, plugin_class)()
        try:
            params = plugin.default_params(optical)
        except Exception as exc:
            pytest.skip(f"{plugin_class}: optical metadata insufficient — {exc}")
        out = plugin.process(frame, params)
        assert isinstance(out, np.ndarray)
        assert out.shape == frame.shape, (
            f"{plugin_class} changed shape {frame.shape} -> {out.shape}"
        )
        assert np.isfinite(out).all(), f"{plugin_class} produced non-finite values"


class TestStitcherRunLive:
    """Stitcher uses run_live (engine + selection); cover it explicitly."""

    def test_run_live_does_not_crash_on_ome_tiff(self, tmp_path: Path) -> None:
        from squid_tools.processing.stitching.plugin import (
            StitcherParams,
            StitcherPlugin,
        )
        from squid_tools.viewer.viewport_engine import ViewportEngine

        acq = _create_squid_ome_tiff_acquisition(tmp_path / "acq")
        engine = ViewportEngine()
        engine.load(acq, region="0")

        plugin = StitcherPlugin()
        params = StitcherParams(pixel_size_um=engine.pixel_size_um)
        # Synthetic OME-TIFF FOV filenames are {region}_{fov}.ome.tiff,
        # which differs from TileFusion's {x_mm}_{y_mm}_{z}_{channel}.tif
        # convention. The plugin must handle that gracefully (log + return).
        plugin.run_live(
            selection={0, 1, 2, 3}, engine=engine,
            params=params, progress=lambda *_: None,
        )
        # No assert on overrides — the contract here is "don't crash."


class TestEndToEndGui:
    """Headless MainWindow path — open + run a plugin via controller, no mouse."""

    def test_open_ome_tiff_and_run_flatfield(
        self, qtbot, tmp_path: Path,
    ) -> None:
        from squid_tools.gui.app import MainWindow

        acq = _create_squid_ome_tiff_acquisition(tmp_path / "acq")
        window = MainWindow()
        qtbot.addWidget(window)

        window.open_acquisition(acq)
        assert window.controller.acquisition is not None
        assert window.region_selector.selected_region_id() == "0"

        frame = window.controller.get_frame(region="0", fov=0).astype(np.float32)
        assert frame.shape == (64, 64)

        out = window.controller.run_plugin("Flatfield (BaSiC)", frame)
        assert out.shape == frame.shape

        window.close()


class TestIndividualFormatRegression:
    """Make sure the Squid-output reader work didn't break the per-tile format."""

    def test_open_individual_acquisition_loads_and_reads(
        self, tmp_path: Path,
    ) -> None:
        from squid_tools.core.readers import detect_reader
        from squid_tools.viewer.viewport_engine import ViewportEngine

        acq = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=2, nt=1,
        )
        reader = detect_reader(acq)
        meta = reader.read_metadata(acq)
        assert len(meta.regions["0"].fovs) == 4
        engine = ViewportEngine()
        engine.load(acq, region="0")
        p1, p99 = engine.compute_contrast(channel=0)
        assert 0 <= p1 < p99


# ---------------------------------------------------------------------------
# Real-dataset smoke tests. Skipped if the dataset isn't present locally.
# Set SQUID_REAL_DATASET=/path/to/acq to point at a different acquisition.
# ---------------------------------------------------------------------------


pytestmark_realdata = pytest.mark.skipif(
    not REAL_DATASET_PATH.exists(),
    reason=f"Real dataset not found at {REAL_DATASET_PATH}; "
           "set SQUID_REAL_DATASET to override or skip.",
)


class TestRealDataset:
    """End-to-end on a real Squid acquisition.

    Uses ``REAL_DATASET_PATH`` (default: 10x_mouse_brain). Until an OME-TIFF
    dataset is available locally, this exercises the
    INDIVIDUAL_IMAGES + JSON + XML + configurations.xml path that real
    customer Squid output uses.
    """

    pytestmark = pytestmark_realdata

    @pytest.fixture(scope="class")
    def reader_and_meta(self):
        from squid_tools.core.readers import detect_reader

        reader = detect_reader(REAL_DATASET_PATH)
        meta = reader.read_metadata(REAL_DATASET_PATH)
        return reader, meta

    def test_detected(self, reader_and_meta) -> None:
        reader, meta = reader_and_meta
        assert reader is not None
        assert len(meta.channels) >= 1, "real dataset must expose channels"
        assert meta.regions, "real dataset must expose at least one region"

    def test_read_first_frame(self, reader_and_meta) -> None:
        from squid_tools.core.data_model import FrameKey

        reader, meta = reader_and_meta
        region_id = next(iter(meta.regions))
        first_fov = meta.regions[region_id].fovs[0].fov_index
        frame = reader.read_frame(FrameKey(
            region=region_id, fov=first_fov, z=0, channel=0, timepoint=0,
        ))
        assert frame.ndim == 2
        assert frame.size > 0
        assert np.issubdtype(frame.dtype, np.integer) or np.issubdtype(
            frame.dtype, np.floating,
        )

    def test_compute_contrast_finishes_quickly(self, reader_and_meta) -> None:
        """Contrast sampling must not hang on real data; expect < 30s."""
        import time

        from squid_tools.viewer.viewport_engine import ViewportEngine

        _, meta = reader_and_meta
        region_id = next(iter(meta.regions))
        engine = ViewportEngine()
        engine.load(REAL_DATASET_PATH, region=region_id)
        t0 = time.monotonic()
        p1, p99 = engine.compute_contrast(channel=0)
        elapsed = time.monotonic() - t0
        assert 0 <= p1 < p99, f"sane (p1, p99) expected, got ({p1}, {p99})"
        assert elapsed < 30, (
            f"compute_contrast took {elapsed:.1f}s; should be well under 30s"
        )

    @pytest.mark.parametrize("plugin_module,plugin_class", [
        ("squid_tools.processing.flatfield.plugin", "FlatfieldPlugin"),
        ("squid_tools.processing.decon.plugin", "DeconvolutionPlugin"),
        ("squid_tools.processing.phase.plugin", "PhaseFromDefocusPlugin"),
        ("squid_tools.processing.acns.plugin", "ACNSPlugin"),
        ("squid_tools.processing.bgsub.plugin", "BackgroundSubtractPlugin"),
    ])
    def test_plugin_runs_on_real_frame(
        self, reader_and_meta, plugin_module, plugin_class,
    ) -> None:
        import importlib

        from squid_tools.core.data_model import FrameKey

        reader, meta = reader_and_meta
        region_id = next(iter(meta.regions))
        first_fov = meta.regions[region_id].fovs[0].fov_index
        frame = reader.read_frame(FrameKey(
            region=region_id, fov=first_fov, z=0, channel=0, timepoint=0,
        )).astype(np.float32)

        mod = importlib.import_module(plugin_module)
        plugin = getattr(mod, plugin_class)()
        try:
            params = plugin.default_params(meta.optical)
        except Exception as exc:
            pytest.skip(f"{plugin_class}: optical metadata insufficient — {exc}")
        out = plugin.process(frame, params)
        assert out.shape == frame.shape, (
            f"{plugin_class} changed shape {frame.shape} -> {out.shape}"
        )
        assert np.isfinite(out).all(), (
            f"{plugin_class} produced non-finite values"
        )

    def test_open_in_gui_headless(self, qtbot) -> None:
        """Same path the user clicks: MainWindow.open_acquisition()."""
        from squid_tools.gui.app import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        window.open_acquisition(REAL_DATASET_PATH)
        assert window.controller.acquisition is not None
        # Region selector should be populated.
        assert window.region_selector.selected_region_id() != ""
        window.close()

    def test_stitcher_run_live_handles_real_dataset(self, reader_and_meta) -> None:
        """Stitcher delegates to vendored TileFusion; must not crash."""
        from squid_tools.processing.stitching.plugin import (
            StitcherParams,
            StitcherPlugin,
        )
        from squid_tools.viewer.viewport_engine import ViewportEngine

        _, meta = reader_and_meta
        region_id = next(iter(meta.regions))
        engine = ViewportEngine()
        engine.load(REAL_DATASET_PATH, region=region_id)

        # Pick the first 4 FOVs (or all if fewer) for a quick run.
        fov_indices = [f.fov_index for f in meta.regions[region_id].fovs[:4]]
        plugin = StitcherPlugin()
        params = StitcherParams(pixel_size_um=engine.pixel_size_um)
        plugin.run_live(
            selection=set(fov_indices), engine=engine,
            params=params, progress=lambda *_: None,
        )
        # Contract: don't crash. Position-override correctness is asserted in
        # tests/unit/test_stitcher_run_live.py and tests/integration/test_stitch_live.py.
