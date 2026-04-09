"""Integration tests using real Squid acquisition data.

These tests are skipped when the real mouse brain dataset is not available
on the local filesystem.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

REAL_DATA = Path.home() / "Downloads" / "10x_mouse_brain_2025-04-23_00-53-11.236590"
skip_no_data = pytest.mark.skipif(
    not REAL_DATA.exists(), reason="Real test data not available"
)


@skip_no_data
def test_detect_format_real():
    from squid_tools.core.readers.detect import detect_format

    fmt = detect_format(REAL_DATA)
    assert fmt.value == "INDIVIDUAL_IMAGES"


@skip_no_data
def test_open_acquisition_real():
    from squid_tools.core.readers.detect import open_acquisition

    acq = open_acquisition(REAL_DATA)
    assert len(acq.channels) == 4
    assert len(acq.regions) >= 1
    assert acq.objective.magnification == 10.0
    assert abs(acq.objective.pixel_size_um - 0.752) < 0.01  # 7.52 * (180/10/180)


@skip_no_data
def test_open_acquisition_mode_manual():
    from squid_tools.core.data_model import AcquisitionMode
    from squid_tools.core.readers.detect import open_acquisition

    acq = open_acquisition(REAL_DATA)
    assert acq.mode == AcquisitionMode.MANUAL


@skip_no_data
def test_open_acquisition_regions():
    from squid_tools.core.readers.detect import open_acquisition

    acq = open_acquisition(REAL_DATA)
    assert "manual" in acq.regions
    assert len(acq.regions["manual"].fovs) == 70


@skip_no_data
def test_read_frame_real():
    from squid_tools.core.data_model import FrameKey
    from squid_tools.core.readers.detect import open_acquisition
    from squid_tools.core.readers.individual import IndividualImageReader

    acq = open_acquisition(REAL_DATA)
    reader = IndividualImageReader()
    # Read first FOV, first channel
    key = FrameKey(region="manual", fov=0, z=0, channel=0, timepoint=0)
    frame = reader.read_frame(REAL_DATA, key)
    assert frame.shape == (2084, 2084)
    assert frame.dtype.name == "uint16"


@skip_no_data
def test_read_different_channels_real():
    from squid_tools.core.data_model import FrameKey
    from squid_tools.core.readers.individual import IndividualImageReader

    reader = IndividualImageReader()
    key0 = FrameKey(region="manual", fov=0, z=0, channel=0, timepoint=0)
    key1 = FrameKey(region="manual", fov=0, z=0, channel=1, timepoint=0)
    f0 = reader.read_frame(REAL_DATA, key0)
    f1 = reader.read_frame(REAL_DATA, key1)
    assert not np.array_equal(f0, f1)


@skip_no_data
def test_read_last_fov_real():
    from squid_tools.core.data_model import FrameKey
    from squid_tools.core.readers.individual import IndividualImageReader

    reader = IndividualImageReader()
    key = FrameKey(region="manual", fov=69, z=0, channel=0, timepoint=0)
    frame = reader.read_frame(REAL_DATA, key)
    assert frame.shape == (2084, 2084)
    assert frame.dtype.name == "uint16"
