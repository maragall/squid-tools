"""Processing plugin abstract base class.

Every processing module implements this interface. Wrapping a new
algorithm = one file, one class, ~50 lines.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import BaseModel

if TYPE_CHECKING:
    from squid_tools.core.data_model import Acquisition, FOVPosition, OpticalMetadata
    from squid_tools.viewer.viewport_engine import ViewportEngine


class ProcessingPlugin(ABC):
    """Base class for all processing plugins.

    Attributes:
        name: Human-readable plugin name.
        category: Plugin category ("stitching", "deconvolution", "correction", "phase").
        requires_gpu: Whether GPU is required (with CPU fallback).
    """

    name: str
    category: str
    requires_gpu: bool = False

    @abstractmethod
    def parameters(self) -> type[BaseModel]:
        """Return the Pydantic model class for this plugin's parameters."""
        ...

    @abstractmethod
    def validate(self, acq: Acquisition) -> list[str]:
        """Validate that this plugin can process the given acquisition.

        Returns list of warning/error messages. Empty list = valid.
        """
        ...

    @abstractmethod
    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        """Process frames. Input and output are numpy arrays."""
        ...

    @abstractmethod
    def default_params(self, optical: OpticalMetadata) -> BaseModel:
        """Return default parameters populated from optical metadata."""
        ...

    @abstractmethod
    def test_cases(self) -> list[dict[str, Any]]:
        """Return synthetic test cases: list of {input, expected} dicts."""
        ...

    def run_live(
        self,
        selection: set[int] | None,
        engine: "ViewportEngine",
        params: BaseModel,
        progress: Callable[[str, int, int], None],
    ) -> None:
        """Run this plugin live with progress feedback.

        Default: iterate the selection (or all FOVs if None), call process()
        on each tile, emit progress per tile.

        Plugins override this for custom live behavior (calibrate-then-apply,
        progressive pairwise registration, etc.).
        """
        indices = selection if selection else engine.all_fov_indices()
        indices_list = sorted(indices)
        total = max(len(indices_list), 1)
        progress("Processing", 0, total)
        for i, fov in enumerate(indices_list):
            frame = engine.get_raw_frame(fov, z=0, channel=0, timepoint=0)
            _ = self.process(frame, params)
            progress("Processing", i + 1, total)

    def process_region(
        self,
        frames: dict[int, np.ndarray],
        positions: list[FOVPosition],
        params: BaseModel,
    ) -> np.ndarray | None:
        """Override for spatial plugins (stitching). Default: not spatial."""
        return None
