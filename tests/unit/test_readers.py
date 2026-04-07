"""Unit tests for FormatReader ABC, format detection, and open_acquisition."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from squid_tools.core.data_model import AcquisitionFormat, AcquisitionMode
from squid_tools.core.readers import FormatReader, detect_format, open_acquisition

# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

def test_format_reader_is_abstract() -> None:
    """FormatReader cannot be instantiated directly."""
    with pytest.raises(TypeError):
        FormatReader()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# detect_format
# ---------------------------------------------------------------------------

def test_detect_individual_images(individual_wellplate: Path) -> None:
    """Timepoint subdirectories with TIFFs → INDIVIDUAL_IMAGES."""
    fmt = detect_format(individual_wellplate)
    assert fmt == AcquisitionFormat.INDIVIDUAL_IMAGES


def test_detect_ome_tiff(ome_tiff_wellplate: Path) -> None:
    """Presence of ome_tiff/ subdirectory → OME_TIFF."""
    fmt = detect_format(ome_tiff_wellplate)
    assert fmt == AcquisitionFormat.OME_TIFF


# ---------------------------------------------------------------------------
# open_acquisition – basic metadata
# ---------------------------------------------------------------------------

def test_open_acquisition_individual(individual_wellplate: Path) -> None:
    """open_acquisition parses INDIVIDUAL_IMAGES wellplate correctly."""
    acq = open_acquisition(individual_wellplate)

    assert acq.format == AcquisitionFormat.INDIVIDUAL_IMAGES
    assert acq.mode == AcquisitionMode.WELLPLATE
    assert acq.path == individual_wellplate

    # Channels
    assert len(acq.channels) == 2
    assert acq.channels[0].name == "Channel0"

    # Regions  (fixture: n_regions=2, region_ids=['R0', 'R1'])
    assert len(acq.regions) == 2
    assert "R0" in acq.regions
    assert "R1" in acq.regions

    # FOVs per region: 3x3 = 9
    assert len(acq.regions["R0"].fovs) == 9

    # Z-stack (nz=2)
    assert acq.z_stack is not None
    assert acq.z_stack.nz == 2

    # Scan
    assert acq.scan.acquisition_pattern == "S-Pattern"


def test_open_acquisition_ome_tiff(ome_tiff_wellplate: Path) -> None:
    """open_acquisition parses OME_TIFF wellplate correctly."""
    acq = open_acquisition(ome_tiff_wellplate)

    assert acq.format == AcquisitionFormat.OME_TIFF
    assert acq.mode == AcquisitionMode.WELLPLATE
    assert len(acq.channels) == 2
    assert len(acq.regions) == 2


def test_open_acquisition_tissue(individual_tissue: Path) -> None:
    """open_acquisition detects flexible mode for tissue acquisitions."""
    acq = open_acquisition(individual_tissue)

    assert acq.mode == AcquisitionMode.FLEXIBLE
    assert acq.format == AcquisitionFormat.INDIVIDUAL_IMAGES
    # Fixture: 1 region, 2x2 = 4 FOVs
    assert len(acq.regions) == 1
    assert len(acq.regions["R0"].fovs) == 4


def test_open_acquisition_pixel_size(individual_wellplate: Path) -> None:
    """pixel_size_um is computed correctly from objective parameters.

    Fixture values:
        sensor_pixel_size_um = 1.85
        camera_binning       = 1
        tube_lens_f_mm       = 180.0
        magnification        = 20.0
        tube_lens_mm         = 180.0  (from acquisition parameters.json)

    Formula: sensor * binning * (tube_lens_f / magnification / tube_lens_mm)
           = 1.85 * 1 * (180 / 20 / 180) = 1.85 * 0.05 = 0.0925
    """
    acq = open_acquisition(individual_wellplate)
    expected = 1.85 * 1 * (180.0 / 20.0 / 180.0)
    assert acq.objective.pixel_size_um == pytest.approx(expected, rel=1e-6)
    assert acq.optical.pixel_size_um == pytest.approx(expected, rel=1e-6)


# ---------------------------------------------------------------------------
# IndividualImageReader – frame reading
# ---------------------------------------------------------------------------

def test_individual_reader_read_frame(individual_wellplate: Path) -> None:
    """IndividualImageReader.read_frame returns the correct frame shape and dtype."""
    from squid_tools.core.readers.individual import IndividualImageReader
    from squid_tools.core.data_model import FrameKey

    reader = IndividualImageReader()
    assert reader.detect(individual_wellplate)

    # Fixture: nz=2 → z-suffixed filenames; region R0, fov 0, z 0, ch 0, t 0
    key = FrameKey(region="R0", fov=0, z=0, channel=0, timepoint=0)
    frame = reader.read_frame(individual_wellplate, key)
    assert frame.shape == (256, 256)
    assert frame.dtype == np.uint16


def test_individual_reader_different_channels(individual_wellplate: Path) -> None:
    """Frames from different channels contain distinct pixel data."""
    from squid_tools.core.readers.individual import IndividualImageReader
    from squid_tools.core.data_model import FrameKey

    reader = IndividualImageReader()
    key_ch0 = FrameKey(region="R0", fov=0, z=0, channel=0, timepoint=0)
    key_ch1 = FrameKey(region="R0", fov=0, z=0, channel=1, timepoint=0)
    frame0 = reader.read_frame(individual_wellplate, key_ch0)
    frame1 = reader.read_frame(individual_wellplate, key_ch1)
    assert not np.array_equal(frame0, frame1)
