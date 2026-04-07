"""Abstract base class for Squid acquisition format readers."""

from __future__ import annotations

import abc
from pathlib import Path

import numpy as np

from squid_tools.core.data_model import Acquisition, FrameKey


class FormatReader(abc.ABC):
    """Abstract base class for all Squid acquisition format readers.

    Subclasses must implement :meth:`detect`, :meth:`read_metadata`,
    and :meth:`read_frame`.
    """

    @classmethod
    @abc.abstractmethod
    def detect(cls, path: Path) -> bool:
        """Return True if *path* is an acquisition directory this reader handles."""

    @abc.abstractmethod
    def read_metadata(self, path: Path) -> Acquisition:
        """Parse acquisition metadata from *path* and return an :class:`Acquisition`."""

    @abc.abstractmethod
    def read_frame(self, path: Path, key: FrameKey) -> np.ndarray:
        """Load and return a single 2-D frame identified by *key*."""
