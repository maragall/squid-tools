"""Squid acquisition format readers."""

from squid_tools.core.readers.base import FormatReader
from squid_tools.core.readers.detect import detect_format, open_acquisition

__all__ = ["FormatReader", "detect_format", "open_acquisition"]
