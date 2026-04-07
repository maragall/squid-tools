"""OME-TIFF format reader for Squid acquisitions."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import tifffile

from squid_tools.core.data_model import Acquisition, FrameKey
from squid_tools.core.readers.base import FormatReader


class OMETiffReader(FormatReader):
    """Read frames from Squid's OME-TIFF acquisition format.

    File pattern: ``ome_tiff/{region}_{fov:05d}.ome.tiff``
    Expected axis order: TZCYX (time, z, channel, y, x).

    If tifffile squeezes the time dimension (e.g. nt=1), the returned
    array may have fewer dimensions; all cases are handled gracefully.
    """

    @classmethod
    def detect(cls, path: Path) -> bool:
        """Return True if *path* contains an ``ome_tiff/`` subdirectory with OME-TIFF files."""
        ome_dir = path / "ome_tiff"
        if not ome_dir.is_dir():
            return False
        return any(ome_dir.glob("*.ome.tiff")) or any(ome_dir.glob("*.ome.tif"))

    def read_metadata(self, path: Path) -> Acquisition:
        raise NotImplementedError("Use open_acquisition() for metadata parsing")

    def read_frame(self, path: Path, key: FrameKey) -> np.ndarray:
        """Load and return a single 2-D frame identified by *key*.

        Parameters
        ----------
        path:
            Root acquisition directory.
        key:
            Frame identifier (region, fov, z, channel, timepoint).

        Returns
        -------
        np.ndarray
            2-D array of shape (height, width).

        Raises
        ------
        FileNotFoundError
            If the expected OME-TIFF file does not exist.
        """
        ome_dir = path / "ome_tiff"
        fname = f"{key.region}_{key.fov:05d}.ome.tiff"
        fpath = ome_dir / fname
        if not fpath.exists():
            raise FileNotFoundError(f"OME-TIFF not found: {fpath}")

        with tifffile.TiffFile(str(fpath)) as tf:
            data = tf.asarray()

        if data.ndim == 5:  # (T, Z, C, Y, X)
            return data[key.timepoint, key.z, key.channel]
        elif data.ndim == 4:  # (Z, C, Y, X) — T was squeezed
            return data[key.z, key.channel]
        elif data.ndim == 3:  # (C, Y, X) — T and Z were squeezed
            return data[key.channel]
        else:
            return data
