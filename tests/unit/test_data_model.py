"""Tests for the Pydantic v2 data model."""

from pathlib import Path

from squid_tools.core.data_model import (
    AcquisitionChannel,
    AcquisitionFormat,
    AcquisitionMode,
    FOVPosition,
    GridParams,
    ObjectiveMetadata,
    Region,
    ScanConfig,
    TimeSeriesConfig,
    ZStackConfig,
)
from tests.fixtures.generate_fixtures import create_individual_acquisition


class TestEnums:
    def test_acquisition_format_values(self) -> None:
        assert AcquisitionFormat.OME_TIFF == "OME_TIFF"
        assert AcquisitionFormat.INDIVIDUAL_IMAGES == "INDIVIDUAL_IMAGES"
        assert AcquisitionFormat.ZARR == "ZARR"

    def test_acquisition_mode_values(self) -> None:
        assert AcquisitionMode.WELLPLATE == "wellplate"
        assert AcquisitionMode.FLEXIBLE == "flexible"
        assert AcquisitionMode.MANUAL == "manual"


class TestObjectiveMetadata:
    def test_create_objective(self) -> None:
        obj = ObjectiveMetadata(
            name="20x",
            magnification=20.0,
            pixel_size_um=0.325,
            numerical_aperture=0.75,
        )
        assert obj.name == "20x"
        assert obj.magnification == 20.0
        assert obj.pixel_size_um == 0.325
        assert obj.numerical_aperture == 0.75

    def test_optional_fields_default_none(self) -> None:
        obj = ObjectiveMetadata(
            name="10x",
            magnification=10.0,
            pixel_size_um=0.65,
        )
        assert obj.numerical_aperture is None
        assert obj.tube_lens_f_mm is None
        assert obj.sensor_pixel_size_um is None
        assert obj.camera_binning == 1


class TestAcquisitionChannel:
    def test_create_channel(self) -> None:
        ch = AcquisitionChannel(
            name="BF LED matrix full",
            illumination_source="LED matrix",
            illumination_intensity=50.0,
            exposure_time_ms=10.0,
        )
        assert ch.name == "BF LED matrix full"
        assert ch.emission_wavelength_nm is None
        assert ch.z_offset_um == 0.0


class TestFOVPosition:
    def test_create_fov(self) -> None:
        fov = FOVPosition(fov_index=0, x_mm=1.5, y_mm=2.3)
        assert fov.fov_index == 0
        assert fov.z_um is None

    def test_fov_with_z(self) -> None:
        fov = FOVPosition(fov_index=3, x_mm=1.0, y_mm=2.0, z_um=100.0, z_piezo_um=5.0)
        assert fov.z_um == 100.0
        assert fov.z_piezo_um == 5.0


class TestRegion:
    def test_create_wellplate_region(self) -> None:
        region = Region(
            region_id="A1",
            center_mm=(10.0, 20.0, 0.0),
            shape="Square",
            fovs=[FOVPosition(fov_index=0, x_mm=9.5, y_mm=19.5)],
            grid_params=GridParams(scan_size_mm=1.0, overlap_percent=15.0, nx=3, ny=3),
        )
        assert region.region_id == "A1"
        assert region.grid_params is not None
        assert region.grid_params.nx == 3

    def test_create_manual_region(self) -> None:
        region = Region(
            region_id="manual0",
            center_mm=(5.0, 5.0, 0.0),
            shape="Manual",
            fovs=[FOVPosition(fov_index=0, x_mm=5.0, y_mm=5.0)],
        )
        assert region.grid_params is None


class TestScanConfig:
    def test_default_scan(self) -> None:
        scan = ScanConfig(
            acquisition_pattern="S-Pattern",
            fov_pattern="Unidirectional",
        )
        assert scan.overlap_percent is None


class TestZStackConfig:
    def test_create_zstack(self) -> None:
        zs = ZStackConfig(nz=10, delta_z_mm=0.001, direction="FROM_BOTTOM")
        assert zs.use_piezo is False


class TestTimeSeriesConfig:
    def test_create_timeseries(self) -> None:
        ts = TimeSeriesConfig(nt=100, delta_t_s=0.5)
        assert ts.nt == 100


class TestFixtureGenerator:
    def test_creates_acquisition_yaml(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1)
        assert (acq_path / "acquisition.yaml").exists()

    def test_creates_coordinates_csv(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1)
        assert (acq_path / "0" / "coordinates.csv").exists()

    def test_creates_image_files(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1)
        tiffs = list((acq_path / "0").glob("*.tiff"))
        assert len(tiffs) == 4  # 2x2 FOVs * 1 channel
