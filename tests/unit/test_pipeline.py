import dask.array as da
import numpy as np
from pydantic import BaseModel

from squid_tools.core.pipeline import Pipeline
from squid_tools.plugins.base import ProcessingPlugin, TestCase


class ScaleParams(BaseModel):
    factor: float = 2.0


class ScalePlugin(ProcessingPlugin):
    name = "Scale"
    category = "correction"

    def parameters(self):
        return ScaleParams

    def validate(self, acq):
        return []

    def process(self, frames, params):
        return frames * params.factor

    def default_params(self, optical):
        return ScaleParams()

    def test_cases(self):
        return [TestCase(name="scale", input_shape=(1, 1, 1, 8, 8))]


def test_pipeline_single_plugin():
    data = da.from_array(np.ones((1, 1, 1, 8, 8), dtype=np.float64))
    pipe = Pipeline()
    pipe.add(ScalePlugin(), ScaleParams(factor=3.0))
    result = pipe.run(data)
    np.testing.assert_array_equal(result.compute(), np.full((1, 1, 1, 8, 8), 3.0))


def test_pipeline_chained():
    data = da.from_array(np.ones((1, 1, 1, 8, 8), dtype=np.float64))
    pipe = Pipeline()
    pipe.add(ScalePlugin(), ScaleParams(factor=2.0))
    pipe.add(ScalePlugin(), ScaleParams(factor=3.0))
    result = pipe.run(data)
    np.testing.assert_array_equal(result.compute(), np.full((1, 1, 1, 8, 8), 6.0))


def test_pipeline_empty():
    data = da.from_array(np.ones((1, 1, 1, 8, 8), dtype=np.float64))
    pipe = Pipeline()
    result = pipe.run(data)
    np.testing.assert_array_equal(result.compute(), data.compute())
