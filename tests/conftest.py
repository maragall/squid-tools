"""Pytest configuration and shared fixtures for squid-tools test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.generate_fixtures import create_test_acquisition

# ---------------------------------------------------------------------------
# GPU detection
# ---------------------------------------------------------------------------

def _check_gpu_available() -> bool:
    try:
        import cupy as cp
        _ = cp.cuda.Device(0).compute_capability  # triggers a real CUDA check
        return True
    except Exception:
        return False


GPU_AVAILABLE: bool = _check_gpu_available()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "gpu: mark test as requiring an NVIDIA GPU with CUDA",
    )


# ---------------------------------------------------------------------------
# Temp directory fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def tmp_acq_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session-scoped temporary directory for acquisition fixtures."""
    return tmp_path_factory.mktemp("acquisitions")


# ---------------------------------------------------------------------------
# INDIVIDUAL_IMAGES fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def individual_wellplate(tmp_acq_dir: Path) -> Path:
    """INDIVIDUAL_IMAGES, wellplate, 2 regions, 3x3 grid, 2 z-slices, 2 channels."""
    acq_dir = tmp_acq_dir / "individual_wellplate"
    return create_test_acquisition(
        acq_dir,
        fmt="INDIVIDUAL_IMAGES",
        widget_type="wellplate",
        n_regions=2,
        nx=3,
        ny=3,
        nz=2,
        nt=1,
        n_channels=2,
        img_shape=(256, 256),
    )


@pytest.fixture(scope="session")
def individual_tissue(tmp_acq_dir: Path) -> Path:
    """INDIVIDUAL_IMAGES, flexible, 1 region, 2x2 grid, 1 z-slice, 2 channels."""
    acq_dir = tmp_acq_dir / "individual_tissue"
    return create_test_acquisition(
        acq_dir,
        fmt="INDIVIDUAL_IMAGES",
        widget_type="flexible",
        n_regions=1,
        nx=2,
        ny=2,
        nz=1,
        nt=1,
        n_channels=2,
        img_shape=(256, 256),
    )


# ---------------------------------------------------------------------------
# OME-TIFF fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def ome_tiff_wellplate(tmp_acq_dir: Path) -> Path:
    """OME_TIFF, wellplate, 2 regions, 3x3 grid, 2 z-slices, 2 channels."""
    acq_dir = tmp_acq_dir / "ome_tiff_wellplate"
    return create_test_acquisition(
        acq_dir,
        fmt="OME_TIFF",
        widget_type="wellplate",
        n_regions=2,
        nx=3,
        ny=3,
        nz=2,
        nt=1,
        n_channels=2,
        img_shape=(256, 256),
    )


@pytest.fixture(scope="session")
def ome_tiff_tissue(tmp_acq_dir: Path) -> Path:
    """OME_TIFF, flexible, 1 region, 2x2 grid, 1 z-slice, 2 channels."""
    acq_dir = tmp_acq_dir / "ome_tiff_tissue"
    return create_test_acquisition(
        acq_dir,
        fmt="OME_TIFF",
        widget_type="flexible",
        n_regions=1,
        nx=2,
        ny=2,
        nz=1,
        nt=1,
        n_channels=2,
        img_shape=(256, 256),
    )


# ---------------------------------------------------------------------------
# GPU marker
# ---------------------------------------------------------------------------

@pytest.fixture
def gpu() -> None:
    """Skip test if no CUDA GPU is available."""
    if not GPU_AVAILABLE:
        pytest.skip("No CUDA GPU available")
