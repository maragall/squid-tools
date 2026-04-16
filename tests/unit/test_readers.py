"""Tests for format readers."""

from pathlib import Path

import numpy as np

from squid_tools.core.data_model import AcquisitionFormat, FrameKey
from squid_tools.core.readers import detect_reader
from squid_tools.core.readers.individual import IndividualImageReader
from squid_tools.core.readers.ome_tiff import OMETiffReader
from squid_tools.core.readers.zarr_reader import ZarrReader


class TestIndividualImageReader:
    def test_detect_individual_format(self, individual_acquisition: Path) -> None:
        assert IndividualImageReader.detect(individual_acquisition) is True

    def test_detect_rejects_ome_tiff(self, ome_tiff_acquisition: Path) -> None:
        assert IndividualImageReader.detect(ome_tiff_acquisition) is False

    def test_read_metadata_format(self, individual_acquisition: Path) -> None:
        reader = IndividualImageReader()
        acq = reader.read_metadata(individual_acquisition)
        assert acq.format == AcquisitionFormat.INDIVIDUAL_IMAGES

    def test_read_metadata_regions(self, individual_acquisition: Path) -> None:
        reader = IndividualImageReader()
        acq = reader.read_metadata(individual_acquisition)
        assert "0" in acq.regions
        assert len(acq.regions["0"].fovs) == 9  # 3x3 grid

    def test_read_metadata_channels(self, individual_acquisition: Path) -> None:
        reader = IndividualImageReader()
        acq = reader.read_metadata(individual_acquisition)
        assert len(acq.channels) == 2

    def test_read_metadata_objective(self, individual_acquisition: Path) -> None:
        reader = IndividualImageReader()
        acq = reader.read_metadata(individual_acquisition)
        assert acq.objective.pixel_size_um == 0.325
        assert acq.objective.magnification == 20.0

    def test_read_frame(self, individual_acquisition: Path) -> None:
        reader = IndividualImageReader()
        reader.read_metadata(individual_acquisition)
        key = FrameKey(region="0", fov=0, z=0, channel=0, timepoint=0)
        frame = reader.read_frame(key)
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (128, 128)
        assert frame.dtype == np.uint16


class TestOMETiffReader:
    def test_detect_ome_tiff_format(self, ome_tiff_acquisition: Path) -> None:
        assert OMETiffReader.detect(ome_tiff_acquisition) is True

    def test_detect_rejects_individual(self, individual_acquisition: Path) -> None:
        assert OMETiffReader.detect(individual_acquisition) is False

    def test_read_metadata_format(self, ome_tiff_acquisition: Path) -> None:
        reader = OMETiffReader()
        acq = reader.read_metadata(ome_tiff_acquisition)
        assert acq.format == AcquisitionFormat.OME_TIFF

    def test_read_metadata_regions(self, ome_tiff_acquisition: Path) -> None:
        reader = OMETiffReader()
        acq = reader.read_metadata(ome_tiff_acquisition)
        assert "0" in acq.regions
        assert len(acq.regions["0"].fovs) == 4  # 2x2 grid

    def test_read_frame(self, ome_tiff_acquisition: Path) -> None:
        reader = OMETiffReader()
        reader.read_metadata(ome_tiff_acquisition)
        key = FrameKey(region="0", fov=0, z=0, channel=0, timepoint=0)
        frame = reader.read_frame(key)
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (128, 128)
        assert frame.dtype == np.uint16


class TestZarrReader:
    def test_detect_zarr_format(self, zarr_hcs_acquisition: Path) -> None:
        assert ZarrReader.detect(zarr_hcs_acquisition) is True

    def test_detect_rejects_individual(self, individual_acquisition: Path) -> None:
        assert ZarrReader.detect(individual_acquisition) is False

    def test_read_metadata_format(self, zarr_hcs_acquisition: Path) -> None:
        reader = ZarrReader()
        acq = reader.read_metadata(zarr_hcs_acquisition)
        assert acq.format == AcquisitionFormat.ZARR

    def test_read_metadata_regions(self, zarr_hcs_acquisition: Path) -> None:
        reader = ZarrReader()
        acq = reader.read_metadata(zarr_hcs_acquisition)
        assert "0" in acq.regions
        assert len(acq.regions["0"].fovs) == 4  # 2x2 grid

    def test_read_frame(self, zarr_hcs_acquisition: Path) -> None:
        reader = ZarrReader()
        reader.read_metadata(zarr_hcs_acquisition)
        key = FrameKey(region="0", fov=0, z=0, channel=0, timepoint=0)
        frame = reader.read_frame(key)
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (128, 128)
        assert frame.dtype == np.uint16


class TestDetectReader:
    def test_detect_individual(self, individual_acquisition: Path) -> None:
        reader = detect_reader(individual_acquisition)
        assert isinstance(reader, IndividualImageReader)

    def test_detect_ome_tiff(self, ome_tiff_acquisition: Path) -> None:
        reader = detect_reader(ome_tiff_acquisition)
        assert isinstance(reader, OMETiffReader)


class TestIndividualReaderLargeCSV:
    def test_large_csv_streaming(self, tmp_path: Path) -> None:
        """Reader should handle large CSVs without materializing all dicts."""
        import csv as csv_mod
        acq_path = tmp_path / "large_acq"
        acq_path.mkdir(parents=True)
        tp_dir = acq_path / "0"
        tp_dir.mkdir()

        # Write a 1000-row coordinates.csv
        rows = []
        for i in range(1000):
            rows.append({
                "region": "0",
                "fov": i,
                "z_level": 0,
                "x (mm)": (i % 100) * 0.1,
                "y (mm)": (i // 100) * 0.1,
                "z (um)": 0.0,
                "time": 0.0,
            })
        with open(tp_dir / "coordinates.csv", "w", newline="") as f:
            writer = csv_mod.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

        # Write a minimal tiff + acquisition files
        import numpy as np
        import tifffile
        import yaml

        img = np.zeros((128, 128), dtype=np.uint16)
        tifffile.imwrite(str(tp_dir / "0_0_0_ch.tiff"), img)

        acq_yaml = {
            "acquisition": {"widget_type": "wellplate"},
            "objective": {"name": "20x", "magnification": 20.0, "pixel_size_um": 0.325},
            "z_stack": {"nz": 1, "delta_z_mm": 0.001, "config": "FROM_BOTTOM", "use_piezo": False},
            "time_series": {"nt": 1, "delta_t_s": 1.0},
            "channels": [{"name": "ch", "camera_settings": {"exposure_time_ms": 10.0},
                          "illumination_settings": {"illumination_channel": "LED_0",
                                                    "intensity": 50.0}, "z_offset_um": 0.0}],
        }
        with open(acq_path / "acquisition.yaml", "w") as f:
            yaml.dump(acq_yaml, f)
        import json
        with open(acq_path / "acquisition parameters.json", "w") as f:
            json.dump({"sensor_pixel_size_um": 3.45, "tube_lens_mm": 50.0}, f)

        reader = IndividualImageReader()
        acq = reader.read_metadata(acq_path)
        assert "0" in acq.regions
        assert len(acq.regions["0"].fovs) == 1000


class TestIndividualReaderNoYaml:
    def test_detect_without_yaml(self, tmp_path: Path) -> None:
        """Reader should detect acquisitions that only have JSON + coordinates."""
        from tests.fixtures.generate_fixtures import create_individual_acquisition
        acq_path = create_individual_acquisition(tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1)
        # Remove the yaml
        (acq_path / "acquisition.yaml").unlink()
        assert IndividualImageReader.detect(acq_path) is True

    def test_read_metadata_without_yaml(self, tmp_path: Path) -> None:
        from tests.fixtures.generate_fixtures import create_individual_acquisition
        acq_path = create_individual_acquisition(tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1)
        (acq_path / "acquisition.yaml").unlink()
        reader = IndividualImageReader()
        acq = reader.read_metadata(acq_path)
        assert acq.format == AcquisitionFormat.INDIVIDUAL_IMAGES
        assert len(acq.regions) > 0
        assert len(acq.channels) > 0
