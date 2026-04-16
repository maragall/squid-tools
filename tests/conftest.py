"""Shared test fixtures for squid-tools."""

from pathlib import Path

import pytest

from tests.fixtures.generate_fixtures import (
    create_individual_acquisition,
    create_ome_tiff_acquisition,
    create_zarr_hcs_acquisition,
)


@pytest.fixture
def tmp_acquisition(tmp_path: Path) -> Path:
    """Return a temporary directory for creating test acquisitions."""
    return tmp_path / "test_acquisition"


@pytest.fixture
def individual_acquisition(tmp_path: Path) -> Path:
    """Create a 3x3 individual images acquisition with 2 channels, 2 z-levels."""
    return create_individual_acquisition(
        tmp_path / "individual_acq", nx=3, ny=3, nz=2, nc=2, nt=1
    )


@pytest.fixture
def ome_tiff_acquisition(tmp_path: Path) -> Path:
    """Create a 2x2 OME-TIFF acquisition with 2 channels, 3 z-levels."""
    return create_ome_tiff_acquisition(
        tmp_path / "ome_acq", nx=2, ny=2, nz=3, nc=2, nt=1
    )


@pytest.fixture
def zarr_hcs_acquisition(tmp_path: Path) -> Path:
    """Create a 2x2 Zarr HCS acquisition with 2 channels, 3 z-levels."""
    return create_zarr_hcs_acquisition(
        tmp_path / "zarr_acq", nx=2, ny=2, nz=3, nc=2, nt=1
    )
