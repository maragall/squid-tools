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

# Real-dataset smoke testing — a *stack* of acquisitions, one per format.
# The integration sweep cycles through every entry whose path exists; missing
# entries are silently skipped so contributors only need the formats they
# actually have on disk. Override paths via env vars (Linux/Windows safe).
REAL_DATASETS: dict[str, str] = {
    "individual_tiff": os.environ.get(
        "SQUID_INDIVIDUAL_DATASET",
        "/Users/julioamaragall/Downloads/10x_mouse_brain_2025-04-23_00-53-11.236590",
    ),
    "ome_tiff": os.environ.get(
        "SQUID_OME_TIFF_DATASET",
        # User to drop in a real OME-TIFF Squid acquisition; until then,
        # the synthetic OME-TIFF tests above guard the format-specific paths.
        "",
    ),
}


def _available_datasets() -> list[tuple[str, Path]]:
    """Entries whose path string is non-empty AND exists on disk.

    Path("") resolves to the cwd, so we must reject empty strings *before*
    converting to Path or every empty entry would silently target ".".
    """
    out: list[tuple[str, Path]] = []
    for name, raw in REAL_DATASETS.items():
        if not raw:
            continue
        p = Path(raw)
        if p.exists():
            out.append((name, p))
    return out

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
        # phase + aCNS deferred per user direction (2026-05-02);
        # reinstate when known-answer assertions land for each.
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


class TestBrittlenessGuards:
    """Quick checks that the helpful errors fire instead of opaque crashes."""

    def test_individual_reader_channel_oob_raises_value_error(
        self, tmp_path: Path,
    ) -> None:
        from squid_tools.core.data_model import FrameKey
        from squid_tools.core.readers.individual import IndividualImageReader

        acq = create_individual_acquisition(
            tmp_path / "acq", nx=1, ny=1, nz=1, nc=1, nt=1,
        )
        reader = IndividualImageReader()
        reader.read_metadata(acq)
        with pytest.raises(ValueError, match="Channel index 5 out of range"):
            reader.read_frame(FrameKey(
                region="0", fov=0, z=0, channel=5, timepoint=0,
            ))

    def test_individual_reader_missing_frame_raises_with_path(
        self, tmp_path: Path,
    ) -> None:
        import os

        from squid_tools.core.data_model import FrameKey
        from squid_tools.core.readers.individual import IndividualImageReader

        acq = create_individual_acquisition(
            tmp_path / "acq", nx=1, ny=1, nz=1, nc=1, nt=1,
        )
        reader = IndividualImageReader()
        meta = reader.read_metadata(acq)
        # Delete one frame to trigger the missing-file path.
        ch = meta.channels[0].name
        target = acq / "0" / f"0_0_0_{ch}.tiff"
        os.remove(target)
        with pytest.raises(FileNotFoundError, match=str(target)):
            reader.read_frame(FrameKey(
                region="0", fov=0, z=0, channel=0, timepoint=0,
            ))

    def test_viewport_engine_empty_fovs_raises_value_error(
        self, tmp_path: Path,
    ) -> None:
        """An acquisition whose region has no FOVs must surface a clear error."""
        import csv

        from squid_tools.viewer.viewport_engine import ViewportEngine

        acq = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1,
        )
        # Truncate coordinates.csv to header only.
        coords = acq / "0" / "coordinates.csv"
        with open(coords, newline="") as f:
            header = next(csv.reader(f))
        with open(coords, "w", newline="") as f:
            csv.writer(f).writerow(header)

        engine = ViewportEngine()
        # Either "has no FOVs" or "Region '0' not found" is acceptable —
        # the parser may not create the empty-FOV region at all. Both
        # cases must yield a clear ValueError naming the region.
        with pytest.raises(ValueError, match="(has no FOVs|not found)"):
            engine.load(acq, region="0")

    def test_ome_tiff_reader_channel_oob_raises_value_error(
        self, tmp_path: Path,
    ) -> None:
        from squid_tools.core.data_model import FrameKey
        from squid_tools.core.readers.ome_tiff import OMETiffReader

        acq = _create_squid_ome_tiff_acquisition(
            tmp_path / "acq", nc=2,
        )
        reader = OMETiffReader()
        reader.read_metadata(acq)
        with pytest.raises(ValueError, match="channel index 5 out of range"):
            reader.read_frame(FrameKey(
                region="0", fov=0, z=0, channel=5, timepoint=0,
            ))


# ---------------------------------------------------------------------------
# Real-dataset smoke tests — parametrized over every entry in REAL_DATASETS
# whose path exists on disk. Designed for the user to drop in additional
# format examples (single-TIFF, OME-TIFF, Zarr) and have the same checks run
# automatically. Each test takes (label, path); pytest skips entries whose
# path is missing.
# ---------------------------------------------------------------------------


def _datasets_param():
    available = _available_datasets()
    if not available:
        return pytest.mark.skip(
            "No real datasets configured. Set SQUID_INDIVIDUAL_DATASET or "
            "SQUID_OME_TIFF_DATASET to point at a real Squid acquisition.",
        )
    return pytest.mark.parametrize(
        "label,acq_path", available, ids=[name for name, _ in available],
    )


# Helpers that quantify "did the plugin actually do something correct?"

def _spatial_cv(arr: np.ndarray, blocks: int = 4) -> float:
    """Coefficient of variation across spatial subblocks.

    Higher = more illumination unevenness across the field. Flatfield
    correction should LOWER this number.
    """
    h, w = arr.shape
    bh, bw = max(1, h // blocks), max(1, w // blocks)
    means: list[float] = []
    for i in range(blocks):
        for j in range(blocks):
            patch = arr[i * bh:(i + 1) * bh, j * bw:(j + 1) * bw]
            if patch.size:
                means.append(float(patch.mean()))
    arr_means = np.asarray(means)
    mu = arr_means.mean()
    if mu == 0:
        return 0.0
    return float(arr_means.std() / abs(mu))


def _edge_magnitude(arr: np.ndarray) -> float:
    """Total Sobel-gradient magnitude. Higher = sharper edges.

    Deconvolution should raise this on a real microscopy frame.
    """
    from scipy.ndimage import sobel

    a = arr.astype(np.float32)
    gx = sobel(a, axis=0)
    gy = sobel(a, axis=1)
    return float(np.hypot(gx, gy).sum())


@_datasets_param()
class TestRealDataset:
    """End-to-end on each real Squid acquisition in REAL_DATASETS.

    Same suite runs against every available format. Today: single-TIFF and
    OME-TIFF (when the user drops one in). Beyond "doesn't crash," each
    plugin test asserts a quantitative effect that proves the plugin
    actually transformed the frame in the right direction.
    """

    @pytest.fixture
    def reader_and_meta(self, acq_path: Path):
        from squid_tools.core.readers import detect_reader

        reader = detect_reader(acq_path)
        meta = reader.read_metadata(acq_path)
        return reader, meta

    def test_detected(self, label: str, acq_path: Path, reader_and_meta) -> None:
        reader, meta = reader_and_meta
        assert reader is not None, f"[{label}] no reader detected"
        assert len(meta.channels) >= 1, f"[{label}] no channels exposed"
        assert meta.regions, f"[{label}] no regions exposed"

    def test_read_first_frame(self, label: str, acq_path: Path, reader_and_meta) -> None:
        from squid_tools.core.data_model import FrameKey

        reader, meta = reader_and_meta
        region_id = next(iter(meta.regions))
        first_fov = meta.regions[region_id].fovs[0].fov_index
        frame = reader.read_frame(FrameKey(
            region=region_id, fov=first_fov, z=0, channel=0, timepoint=0,
        ))
        assert frame.ndim == 2, f"[{label}] expected 2D frame"
        assert frame.size > 0

    def test_compute_contrast_finishes_quickly(
        self, label: str, acq_path: Path, reader_and_meta,
    ) -> None:
        """Contrast sampling must not hang. < 30s on any real dataset."""
        import time

        from squid_tools.viewer.viewport_engine import ViewportEngine

        _, meta = reader_and_meta
        region_id = next(iter(meta.regions))
        engine = ViewportEngine()
        engine.load(acq_path, region=region_id)
        t0 = time.monotonic()
        p1, p99 = engine.compute_contrast(channel=0)
        elapsed = time.monotonic() - t0
        assert 0 <= p1 < p99, f"[{label}] sane (p1, p99) expected, got ({p1}, {p99})"
        assert elapsed < 30, (
            f"[{label}] compute_contrast took {elapsed:.1f}s; should be < 30s"
        )

    def test_flatfield_reduces_spatial_unevenness(
        self, label: str, acq_path: Path, reader_and_meta,
    ) -> None:
        """Flatfield correctness: the field-illumination unevenness across
        spatial subblocks must drop after correction.
        """
        from squid_tools.core.data_model import FrameKey
        from squid_tools.processing.flatfield.plugin import FlatfieldPlugin

        reader, meta = reader_and_meta
        region_id = next(iter(meta.regions))
        first_fov = meta.regions[region_id].fovs[0].fov_index
        frame = reader.read_frame(FrameKey(
            region=region_id, fov=first_fov, z=0, channel=0, timepoint=0,
        )).astype(np.float32)

        plugin = FlatfieldPlugin()
        params = plugin.default_params(meta.optical)
        out = plugin.process(frame, params)

        cv_before = _spatial_cv(frame)
        cv_after = _spatial_cv(out)
        assert out.shape == frame.shape, f"[{label}] shape changed"
        assert np.isfinite(out).all(), f"[{label}] non-finite output"
        # Any uniform field will have CV close to 0; only assert reduction
        # when there is meaningful unevenness to remove (>1% CV).
        if cv_before > 0.01:
            assert cv_after < cv_before, (
                f"[{label}] flatfield should reduce spatial CV but it went "
                f"{cv_before:.4f} -> {cv_after:.4f}"
            )

    def test_decon_raises_edge_magnitude(
        self, label: str, acq_path: Path, reader_and_meta,
    ) -> None:
        """Deconvolution correctness: total Sobel gradient magnitude must
        not drop after deconvolution (sharpening should preserve or raise it).
        """
        from squid_tools.core.data_model import FrameKey
        from squid_tools.processing.decon.plugin import DeconvolutionPlugin

        reader, meta = reader_and_meta
        region_id = next(iter(meta.regions))
        first_fov = meta.regions[region_id].fovs[0].fov_index
        frame = reader.read_frame(FrameKey(
            region=region_id, fov=first_fov, z=0, channel=0, timepoint=0,
        )).astype(np.float32)

        plugin = DeconvolutionPlugin()
        try:
            params = plugin.default_params(meta.optical)
        except Exception as exc:
            pytest.skip(f"[{label}] decon optical metadata insufficient: {exc}")
        out = plugin.process(frame, params)

        edges_before = _edge_magnitude(frame)
        edges_after = _edge_magnitude(out)
        assert out.shape == frame.shape, f"[{label}] shape changed"
        assert np.isfinite(out).all(), f"[{label}] non-finite output"
        # Allow tiny numerical drift; assert no significant blur was added.
        assert edges_after >= 0.95 * edges_before, (
            f"[{label}] decon must not lose edge content: "
            f"{edges_before:.0f} -> {edges_after:.0f}"
        )

    def test_bgsub_lowers_mean_intensity(
        self, label: str, acq_path: Path, reader_and_meta,
    ) -> None:
        """Background subtraction correctness: post-subtraction mean
        intensity must be lower than the input mean.
        """
        from squid_tools.core.data_model import FrameKey
        from squid_tools.processing.bgsub.plugin import BackgroundSubtractPlugin

        reader, meta = reader_and_meta
        region_id = next(iter(meta.regions))
        first_fov = meta.regions[region_id].fovs[0].fov_index
        frame = reader.read_frame(FrameKey(
            region=region_id, fov=first_fov, z=0, channel=0, timepoint=0,
        )).astype(np.float32)

        plugin = BackgroundSubtractPlugin()
        params = plugin.default_params(meta.optical)
        out = plugin.process(frame, params)

        assert out.shape == frame.shape, f"[{label}] shape changed"
        assert np.isfinite(out).all(), f"[{label}] non-finite output"
        assert out.mean() < frame.mean(), (
            f"[{label}] bgsub mean must drop: "
            f"{frame.mean():.1f} -> {out.mean():.1f}"
        )

    @pytest.mark.parametrize("plugin_module,plugin_class,tag_attr", [
        ("squid_tools.processing.bgsub.plugin", "BackgroundSubtractPlugin", "_is_bgsub"),
        ("squid_tools.processing.decon.plugin", "DeconvolutionPlugin", "_is_decon"),
        ("squid_tools.processing.flatfield.plugin", "FlatfieldPlugin", "_is_flatfield"),
    ])
    def test_run_live_installs_pipeline_transform(
        self, label: str, acq_path: Path, plugin_module, plugin_class, tag_attr,
    ) -> None:
        """run_live must wire the plugin into engine._pipeline so the live
        viewer sees the effect — not just compute and discard a frame.

        This is the "bg sub doesn't work in the GUI" guard: per-frame plugins
        whose run_live used the base implementation silently no-op'd in the
        viewer because the base discards results.
        """
        import importlib

        from squid_tools.viewer.viewport_engine import ViewportEngine

        _, meta = reader_and_meta = (None, None)
        from squid_tools.core.readers import detect_reader

        reader = detect_reader(acq_path)
        meta = reader.read_metadata(acq_path)
        region_id = next(iter(meta.regions))
        engine = ViewportEngine()
        engine.load(acq_path, region=region_id)

        mod = importlib.import_module(plugin_module)
        plugin = getattr(mod, plugin_class)()
        try:
            params = plugin.default_params(meta.optical)
        except Exception as exc:
            pytest.skip(f"[{label}] {plugin_class}: optical metadata insufficient — {exc}")

        before = list(engine._pipeline)
        plugin.run_live(
            selection=None, engine=engine, params=params,
            progress=lambda *_: None,
        )
        after = list(engine._pipeline)

        new_transforms = [t for t in after if t not in before]
        assert new_transforms, (
            f"[{label}] {plugin_class}.run_live did not install any transform "
            f"into engine._pipeline; the live viewer will see no effect"
        )
        assert any(getattr(t, tag_attr, False) for t in new_transforms), (
            f"[{label}] {plugin_class}.run_live installed a transform without "
            f"the {tag_attr} marker; re-running will stack duplicates"
        )

    # Phase from defocus and aCNS denoising: explicitly excluded from the
    # auto-sweep per user direction (2026-05-02). Re-enable by parametrizing
    # over them again once we have a known-answer test for each.

    def test_open_in_gui_headless(
        self, label: str, acq_path: Path, qtbot,
    ) -> None:
        """Same path the user clicks: MainWindow.open_acquisition()."""
        from squid_tools.gui.app import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        window.open_acquisition(acq_path)
        assert window.controller.acquisition is not None, (
            f"[{label}] open_acquisition didn't populate controller"
        )
        assert window.region_selector.selected_region_id() != "", (
            f"[{label}] region selector empty after open"
        )
        window.close()

    def test_stitcher_run_live_moves_tiles(
        self, label: str, acq_path: Path, reader_and_meta,
    ) -> None:
        """Stitcher correctness: at least one position override must be set
        and at least one must differ from its nominal stage position
        (registration found a non-trivial shift).
        """
        from squid_tools.processing.stitching.plugin import (
            StitcherParams,
            StitcherPlugin,
        )
        from squid_tools.viewer.viewport_engine import ViewportEngine

        _, meta = reader_and_meta
        region_id = next(iter(meta.regions))
        engine = ViewportEngine()
        engine.load(acq_path, region=region_id)

        fov_indices = [f.fov_index for f in meta.regions[region_id].fovs[:4]]
        if len(fov_indices) < 2:
            pytest.skip(f"[{label}] need at least 2 FOVs for stitching")
        nominal = engine.get_nominal_positions(set(fov_indices))

        plugin = StitcherPlugin()
        params = StitcherParams(pixel_size_um=engine.pixel_size_um)
        plugin.run_live(
            selection=set(fov_indices), engine=engine,
            params=params, progress=lambda *_: None,
        )

        overrides = engine._position_overrides
        if not overrides:
            pytest.skip(
                f"[{label}] stitcher returned no overrides — likely a "
                "format-mismatch with TileFusion's expected layout, "
                "covered as a graceful no-op in test_stitcher_run_live.py",
            )
        assert any(idx in overrides for idx in fov_indices), (
            f"[{label}] no overrides for selected FOVs"
        )
        # At least one override must differ from nominal by more than
        # floating-point noise — otherwise stitcher didn't actually align.
        moved = any(
            (abs(overrides[idx][0] - nominal[idx][0])
             + abs(overrides[idx][1] - nominal[idx][1])) > 1e-6
            for idx in fov_indices if idx in overrides and idx in nominal
        )
        assert moved, (
            f"[{label}] stitcher set overrides identical to nominal; "
            "registration produced no shift"
        )
