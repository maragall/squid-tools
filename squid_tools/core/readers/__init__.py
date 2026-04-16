"""Format readers for Squid acquisition data."""

from __future__ import annotations

from pathlib import Path

from squid_tools.core.readers.base import FormatReader
from squid_tools.core.readers.individual import IndividualImageReader
from squid_tools.core.readers.ome_tiff import OMETiffReader
from squid_tools.core.readers.zarr_reader import ZarrReader

_READERS: list[type[FormatReader]] = [
    ZarrReader,
    OMETiffReader,
    IndividualImageReader,
]


def detect_reader(path: Path) -> FormatReader:
    """Auto-detect the format and return the appropriate reader."""
    for reader_cls in _READERS:
        if reader_cls.detect(path):
            return reader_cls()
    raise ValueError(f"No reader found for acquisition at {path}")
