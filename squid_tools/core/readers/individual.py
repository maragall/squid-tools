"""Reader for Squid's individual image format (one TIFF per frame)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import tifffile

from squid_tools.core.data_model import Acquisition, FrameKey
from squid_tools.core.readers.base import FormatReader


class IndividualImageReader(FormatReader):
    """Read frames from Squid's individual image format.

    File layout
    -----------
    * nz == 1:  ``{path}/{timepoint:05d}/{region}_{fov:05d}_C{ch:02d}.tiff``
    * nz >  1:  ``{path}/{timepoint:05d}/{region}_{fov:05d}_z{z:03d}_C{ch:02d}.tiff``

    :meth:`read_frame` tries the z-suffixed name first so that it works
    transparently for both layouts without the caller needing to know nz.
    """

    @classmethod
    def detect(cls, path: Path) -> bool:
        """Return True when *path* contains 5-digit timepoint dirs with TIFF files."""
        path = Path(path)
        for child in sorted(path.iterdir()):
            if child.is_dir() and child.name.isdigit() and len(child.name) == 5:
                tiffs = list(child.glob("*.tiff")) + list(child.glob("*.tif"))
                if tiffs:
                    return True
        return False

    def read_metadata(self, path: Path) -> Acquisition:
        raise NotImplementedError("Use open_acquisition() for metadata parsing")

    def read_frame(self, path: Path, key: FrameKey) -> np.ndarray:
        """Load and return a single 2-D frame identified by *key*.

        Tries the z-suffixed filename first (nz > 1), then falls back to the
        plain filename (nz == 1).

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
            If neither the z-suffixed nor the plain file exists.
        """
        path = Path(path)
        t_dir = path / f"{key.timepoint:05d}"

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
