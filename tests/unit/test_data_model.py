from squid_tools.core.data_model import (
    Acquisition,
    AcquisitionChannel,
    AcquisitionFormat,
    AcquisitionMode,
    FOVPosition,
    FrameKey,
    GridParams,
    ObjectiveMetadata,
    OpticalMetadata,
    Region,
    ScanConfig,
    TimeSeriesConfig,
    ZStackConfig,
)


def test_acquisition_format_enum():
    assert AcquisitionFormat.OME_TIFF == "OME_TIFF"
    assert AcquisitionFormat.INDIVIDUAL_IMAGES == "INDIVIDUAL_IMAGES"
    assert AcquisitionFormat.ZARR == "ZARR"


def test_acquisition_mode_enum():
    assert AcquisitionMode.WELLPLATE == "wellplate"
    assert AcquisitionMode.FLEXIBLE == "flexible"
    assert AcquisitionMode.MANUAL == "manual"


def test_objective_metadata_validation():
    obj = ObjectiveMetadata(
        name="20x",
        magnification=20.0,
        numerical_aperture=0.75,
        tube_lens_f_mm=200.0,
        sensor_pixel_size_um=3.45,
        camera_binning=1,
        tube_lens_mm=200.0,
    )
    assert obj.name == "20x"
    assert obj.magnification == 20.0


def test_optical_metadata_immersion_defaults():
    opt = OpticalMetadata(
        modality="widefield",
        immersion_medium="water",
        immersion_ri=1.333,
        numerical_aperture=0.75,
        pixel_size_um=0.1725,
    )
    assert opt.immersion_ri == 1.333
    assert opt.dz_um is None


def test_acquisition_channel():
    ch = AcquisitionChannel(
        name="DAPI",
        illumination_source="LED_405",
        illumination_intensity=50.0,
        exposure_time_ms=100.0,
        emission_wavelength_nm=461.0,
    )
    assert ch.z_offset_um == 0.0


def test_scan_config():
    sc = ScanConfig(
        acquisition_pattern="S-Pattern",
        fov_pattern="Unidirectional",
        overlap_percent=15.0,
    )
    assert sc.acquisition_pattern == "S-Pattern"


def test_frame_key():
    fk = FrameKey(region="A1", fov=0, z=3, channel=1, timepoint=0)
    assert fk.region == "A1"
    assert fk.fov == 0


def test_fov_position():
    fov = FOVPosition(fov_index=0, x_mm=1.5, y_mm=2.3)
    assert fov.z_um is None
    assert fov.z_piezo_um is None


def test_region():
    region = Region(
        region_id="A1",
        center_mm=(10.0, 20.0, 0.0),
        shape="Square",
        fovs=[FOVPosition(fov_index=0, x_mm=9.5, y_mm=19.5)],
        grid_params=GridParams(scan_size_mm=2.0, overlap_percent=15.0, nx=3, ny=3),
    )
    assert len(region.fovs) == 1
    assert region.grid_params is not None


def test_zstack_config():
    zs = ZStackConfig(nz=10, delta_z_mm=0.001, direction="FROM_BOTTOM")
    assert zs.use_piezo is False


def test_timeseries_config():
    ts = TimeSeriesConfig(nt=100, delta_t_s=30.0)
    assert ts.nt == 100


def test_acquisition_json_roundtrip():
    acq = Acquisition(
        path="/tmp/test",
        format=AcquisitionFormat.OME_TIFF,
        mode=AcquisitionMode.WELLPLATE,
        objective=ObjectiveMetadata(
            name="20x",
            magnification=20.0,
            numerical_aperture=0.75,
            tube_lens_f_mm=200.0,
            sensor_pixel_size_um=3.45,
            camera_binning=1,
            tube_lens_mm=200.0,
        ),
        optical=OpticalMetadata(
            modality="widefield",
            immersion_medium="air",
            immersion_ri=1.0,
            numerical_aperture=0.75,
            pixel_size_um=0.1725,
        ),
        channels=[
            AcquisitionChannel(
                name="DAPI",
                illumination_source="LED_405",
                illumination_intensity=50.0,
                exposure_time_ms=100.0,
            )
        ],
        scan=ScanConfig(
            acquisition_pattern="S-Pattern",
            fov_pattern="Unidirectional",
        ),
        regions={
            "A1": Region(
                region_id="A1",
                center_mm=(10.0, 20.0, 0.0),
                shape="Square",
                fovs=[FOVPosition(fov_index=0, x_mm=9.5, y_mm=19.5)],
            )
        },
    )
    json_str = acq.model_dump_json()
    restored = Acquisition.model_validate_json(json_str)
    assert restored.format == AcquisitionFormat.OME_TIFF
    assert restored.regions["A1"].region_id == "A1"
