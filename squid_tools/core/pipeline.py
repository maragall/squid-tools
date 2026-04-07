from __future__ import annotations

import dask.array as da
from pydantic import BaseModel

from squid_tools.plugins.base import ProcessingPlugin


class PipelineStep:
    def __init__(self, plugin: ProcessingPlugin, params: BaseModel) -> None:
        self.plugin = plugin
        self.params = params


class Pipeline:
    def __init__(self) -> None:
        self._steps: list[PipelineStep] = []

    def add(self, plugin: ProcessingPlugin, params: BaseModel) -> None:
        self._steps.append(PipelineStep(plugin, params))

    def run(self, frames: da.Array) -> da.Array:
        result = frames
        for step in self._steps:
            result = step.plugin.process(result, step.params)
        return result

    def clear(self) -> None:
        self._steps.clear()

    @property
    def steps(self) -> list[PipelineStep]:
        return list(self._steps)
