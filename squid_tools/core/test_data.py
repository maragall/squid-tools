"""
Test data registry for squid-tools.

Uses pooch to download and cache test datasets from Zenodo.
Datasets are organized by format and acquisition type.

Setup instructions:
1. Create a Zenodo deposit at https://zenodo.org/deposit/new
2. Upload test datasets following the naming convention below
3. Publish the deposit and update ZENODO_DOI with the record DOI
4. Update the registry dict with filenames and their SHA256 hashes

Naming convention for uploaded files:
    ome_tiff_wellplate_3x3.zip       # OME-TIFF, wellplate, 3x3 grid
    ome_tiff_tissue_manual.zip       # OME-TIFF, tissue, manual regions
    individual_wellplate_3x3.zip     # Individual images, wellplate, 3x3 grid
    zarr_hcs_wellplate_96.zip        # Zarr HCS, 96-well plate
    zarr_non_hcs_tissue.zip          # Zarr non-HCS, tissue regions

Each zip contains a complete Squid acquisition directory:
    {name}/
    ├── acquisition.yaml
    ├── coordinates.csv
    ├── acquisition parameters.json
    └── {format-specific files}
"""

import pooch  # type: ignore[import-untyped]

# Update this after publishing the Zenodo deposit
ZENODO_DOI = "10.5281/zenodo.XXXXXXX"
ZENODO_RECORD = "XXXXXXX"

# Base URL for Zenodo record files
ZENODO_URL = f"https://zenodo.org/records/{ZENODO_RECORD}/files/{{fname}}"

# Registry: filename -> SHA256 hash
# Update hashes after uploading files to Zenodo
REGISTRY = {
    # OME-TIFF format
    "ome_tiff_wellplate_3x3.zip": None,  # Set hash after upload
    "ome_tiff_tissue_manual.zip": None,
    # Individual images format
    "individual_wellplate_3x3.zip": None,
    "individual_tissue_manual.zip": None,
    # Zarr format
    "zarr_hcs_wellplate_96.zip": None,
    "zarr_non_hcs_tissue.zip": None,
}

_fetcher = pooch.create(
    path=pooch.os_cache("squid-tools"),
    base_url=ZENODO_URL,
    registry=REGISTRY,
)


def fetch(name: str) -> str:
    """Download and cache a test dataset. Returns path to extracted directory.

    Args:
        name: Dataset filename from REGISTRY (e.g. "ome_tiff_wellplate_3x3.zip")

    Returns:
        Path to the extracted acquisition directory.

    Example:
        path = fetch("ome_tiff_wellplate_3x3.zip")
        acq = Acquisition.from_path(Path(path))
    """
    paths = _fetcher.fetch(name, processor=pooch.Unzip())
    # Unzip returns list of extracted files; find the root directory
    from pathlib import Path

    roots = {Path(p).parts[0] for p in paths}
    if len(roots) == 1:
        return str(Path(paths[0]).parent)
    return str(Path(paths[0]).parent)


def fetch_all() -> dict[str, str]:
    """Download and cache all test datasets. Returns dict of name -> path."""
    return {name: fetch(name) for name in REGISTRY}


def list_datasets() -> list[str]:
    """List available test dataset names."""
    return list(REGISTRY.keys())
