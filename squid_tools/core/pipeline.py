"""Processing pipeline: chains plugin operations sequentially."""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel

from squid_tools.processing.base import ProcessingPlugin


class Pipeline:
    """Chains processing plugins and applies them sequentially to frames."""

    def __init__(self) -> None:
        self._steps: list[tuple[ProcessingPlugin, BaseModel]] = []

    def add(self, plugin: ProcessingPlugin, params: BaseModel) -> None:
        """Add a processing step to the pipeline."""
        self._steps.append((plugin, params))

    def run(self, frames: np.ndarray) -> np.ndarray:
        """Run all pipeline steps on the given frames."""
        result = frames
        for plugin, params in self._steps:
            result = plugin.process(result, params)
        return result

    def clear(self) -> None:
        """Remove all steps from the pipeline."""
        self._steps.clear()

    def __len__(self) -> int:
        return len(self._steps)
