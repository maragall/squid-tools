"""Abstract base class for format readers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from squid_tools.core.data_model import Acquisition, FrameKey


class FormatReader(ABC):
    @classmethod
    @abstractmethod
    def detect(cls, path: Path) -> bool: ...

    @abstractmethod
    def read_metadata(self, path: Path) -> Acquisition: ...

    @abstractmethod
    def read_frame(self, key: FrameKey) -> np.ndarray: ...
