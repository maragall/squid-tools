"""Reader for Squid's individual image format (one TIFF per frame)."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import tifffile

from squid_tools.core.data_model import Acquisition, FrameKey
from squid_tools.core.readers.base import FormatReader

# Regex for real Squid naming: {region}_{fov}_{z}_Fluorescence_{wavelength}_nm_Ex.tiff
_SQUID_REAL_RE = re.compile(
    r"^(.+?)_(\d+)_(\d+)_Fluorescence_(\d+)_nm_Ex\.tiff?$"
)


def _detect_naming_convention(timepoint_dir: Path) -> str:
    """Determine which naming convention a timepoint directory uses.

    Returns
    -------
    ``"squid_real"`` for ``{region}_{fov}_{z}_Fluorescence_{wl}_nm_Ex.tiff``
    ``"legacy"`` for ``{region}_{fov:05d}_C{ch:02d}.tiff`` (with optional z)
    """
    for f in timepoint_dir.iterdir():
        if f.suffix.lower() in (".tiff", ".tif"):
            if _SQUID_REAL_RE.match(f.name):
                return "squid_real"
    return "legacy"


def _get_channel_wavelengths(timepoint_dir: Path) -> list[str]:
    """Return sorted list of wavelength strings found in a timepoint dir."""
    wavelengths: set[str] = set()
    for f in timepoint_dir.iterdir():
        m = _SQUID_REAL_RE.match(f.name)
        if m:
            wavelengths.add(m.group(4))
    return sorted(wavelengths, key=int) if wavelengths else []


class IndividualImageReader(FormatReader):
    """Read frames from Squid's individual image format.

    Supports two file naming conventions:

    **Legacy (synthetic fixtures):**

    * nz == 1:  ``{path}/{timepoint:05d}/{region}_{fov:05d}_C{ch:02d}.tiff``
    * nz >  1:  ``{path}/{timepoint:05d}/{region}_{fov:05d}_z{z:03d}_C{ch:02d}.tiff``

    **Real Squid data:**

    * ``{path}/{timepoint}/{region}_{fov}_{z}_Fluorescence_{wavelength}_nm_Ex.tiff``

    :meth:`read_frame` auto-detects the convention from the directory contents.
    """

    @classmethod
    def detect(cls, path: Path) -> bool:
        """Return True when *path* contains integer-named timepoint dirs with TIFF files."""
        path = Path(path)
        for child in sorted(path.iterdir()):
            if child.is_dir() and child.name.isdigit():
                tiffs = list(child.glob("*.tiff")) + list(child.glob("*.tif"))
                if tiffs:
                    return True
        return False

    def read_metadata(self, path: Path) -> Acquisition:
        raise NotImplementedError("Use open_acquisition() for metadata parsing")

    def read_frame(self, path: Path, key: FrameKey) -> np.ndarray:
        """Load and return a single 2-D frame identified by *key*.

        Auto-detects the naming convention from the timepoint directory
        contents and dispatches accordingly.

        Parameters
        ----------
        path:
            Acquisition root directory.
        key:
            Frame identifier.

        Returns
        -------
        np.ndarray
            2-D array with the frame pixel data.

        Raises
        ------
        FileNotFoundError
            If the file cannot be found under any supported naming convention.
        """
        path = Path(path)

        # Try both zero-padded and non-padded timepoint directory names
        t_dir = path / f"{key.timepoint:05d}"
        if not t_dir.exists():
            t_dir = path / str(key.timepoint)
        if not t_dir.exists():
            raise FileNotFoundError(
                f"Timepoint directory not found: tried "
                f"{key.timepoint:05d} and {key.timepoint} in {path}"
            )

        convention = _detect_naming_convention(t_dir)

        if convention == "squid_real":
            return self._read_frame_squid_real(t_dir, key)
        else:
            return self._read_frame_legacy(t_dir, key)

    def _read_frame_legacy(self, t_dir: Path, key: FrameKey) -> np.ndarray:
        """Read frame using legacy naming convention."""
        fname_z = f"{key.region}_{key.fov:05d}_z{key.z:03d}_C{key.channel:02d}.tiff"
        fname_plain = f"{key.region}_{key.fov:05d}_C{key.channel:02d}.tiff"

        fpath = t_dir / fname_z
        if not fpath.exists():
            fpath = t_dir / fname_plain
        if not fpath.exists():
            raise FileNotFoundError(
                f"Frame not found: tried {fname_z} and {fname_plain} in {t_dir}"
            )

        return tifffile.imread(str(fpath))

    def _read_frame_squid_real(self, t_dir: Path, key: FrameKey) -> np.ndarray:
        """Read frame using real Squid naming convention.

        Maps the integer channel index to a wavelength string by scanning
        the directory for available wavelengths.
        """
        wavelengths = _get_channel_wavelengths(t_dir)
        if not wavelengths:
            raise FileNotFoundError(
                f"No Squid-format TIFF files found in {t_dir}"
            )
        if key.channel >= len(wavelengths):
            raise IndexError(
                f"Channel index {key.channel} out of range; "
                f"found {len(wavelengths)} channels: {wavelengths}"
            )

        wl = wavelengths[key.channel]
        fname = f"{key.region}_{key.fov}_{key.z}_Fluorescence_{wl}_nm_Ex.tiff"
        fpath = t_dir / fname
        if not fpath.exists():
            raise FileNotFoundError(f"Frame not found: {fpath}")

        return tifffile.imread(str(fpath))
