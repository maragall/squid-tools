"""Tests for derived pixel size calculation.

Squid pre-computes pixel_size_um in acquisition.yaml, so normally we
trust that value. But when raw sensor/objective params are available,
we should be able to derive it ourselves using Squid's formula:
    pixel_size_um = sensor_pixel_size_um * binning * (tube_lens_f_mm / magnification / tube_lens_mm)
"""

import math

from squid_tools.core.data_model import ObjectiveMetadata


def test_pixel_size_from_squid_value() -> None:
    """Trust Squid's pre-computed pixel_size_um."""
    obj = ObjectiveMetadata(name="20x", magnification=20.0, pixel_size_um=0.325)
    assert obj.pixel_size_um == 0.325


def test_derive_pixel_size_when_params_available() -> None:
    """Derive pixel_size_um from sensor/objective params (Squid ObjectiveStore formula)."""
    obj = ObjectiveMetadata(
        name="20x",
        magnification=20.0,
        pixel_size_um=0.325,
        sensor_pixel_size_um=3.45,
        tube_lens_f_mm=180.0,
        tube_lens_mm=50.0,
        camera_binning=1,
    )
    # Squid formula: sensor * binning * (obj_tube_lens / mag / sys_tube_lens)
    expected = 3.45 * 1 * (180.0 / 20.0 / 50.0)
    assert math.isclose(obj.derived_pixel_size_um, expected, rel_tol=1e-6)


def test_derived_pixel_size_returns_none_without_params() -> None:
    """Returns None when raw params not available."""
    obj = ObjectiveMetadata(name="20x", magnification=20.0, pixel_size_um=0.325)
    assert obj.derived_pixel_size_um is None
