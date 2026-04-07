from squid_tools.core.data_model import ObjectiveMetadata


def test_pixel_size_20x_standard():
    """20x objective, 200mm tube lens, 3.45um sensor, no binning.
    dxy = 3.45 * 1 * (200 / 20 / 200) = 3.45 * 0.05 = 0.1725 um"""
    obj = ObjectiveMetadata(
        name="20x", magnification=20.0, numerical_aperture=0.75,
        tube_lens_f_mm=200.0, sensor_pixel_size_um=3.45,
        camera_binning=1, tube_lens_mm=200.0,
    )
    assert abs(obj.pixel_size_um - 0.1725) < 1e-10


def test_pixel_size_with_binning():
    """Same setup with 2x binning: 0.345 um"""
    obj = ObjectiveMetadata(
        name="20x", magnification=20.0, numerical_aperture=0.75,
        tube_lens_f_mm=200.0, sensor_pixel_size_um=3.45,
        camera_binning=2, tube_lens_mm=200.0,
    )
    assert abs(obj.pixel_size_um - 0.345) < 1e-10


def test_pixel_size_different_tube_lens():
    """20x with 180mm objective tube lens, 200mm system tube lens.
    lens_factor = 180 / 20 / 200 = 0.045
    dxy = 3.45 * 1 * 0.045 = 0.15525 um"""
    obj = ObjectiveMetadata(
        name="20x Nikon", magnification=20.0, numerical_aperture=0.75,
        tube_lens_f_mm=180.0, sensor_pixel_size_um=3.45,
        camera_binning=1, tube_lens_mm=200.0,
    )
    assert abs(obj.pixel_size_um - 0.15525) < 1e-10


def test_pixel_size_40x():
    """40x, 200mm/200mm tube lens, 3.45um sensor.
    dxy = 3.45 * (200/40/200) = 3.45 * 0.025 = 0.08625 um"""
    obj = ObjectiveMetadata(
        name="40x", magnification=40.0, numerical_aperture=1.3,
        tube_lens_f_mm=200.0, sensor_pixel_size_um=3.45,
        camera_binning=1, tube_lens_mm=200.0,
    )
    assert abs(obj.pixel_size_um - 0.08625) < 1e-10
