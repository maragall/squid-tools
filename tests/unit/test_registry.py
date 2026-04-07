import pytest
from pydantic import BaseModel

from squid_tools.plugins.base import ProcessingPlugin, TestCase


def test_plugin_is_abstract():
    with pytest.raises(TypeError):
        ProcessingPlugin()


def test_test_case_model():
    tc = TestCase(name="identity", input_shape=(1, 1, 1, 64, 64), description="Passthrough")
    assert tc.input_shape == (1, 1, 1, 64, 64)


def test_concrete_plugin():
    class DummyParams(BaseModel):
        sigma: float = 1.0

    class DummyPlugin(ProcessingPlugin):
        name = "Dummy"
        category = "correction"
        requires_gpu = False

        def parameters(self):
            return DummyParams

        def validate(self, acq):
            return []

        def process(self, frames, params):
            return frames

        def default_params(self, optical):
            return DummyParams()

        def test_cases(self):
            return [TestCase(name="pass", input_shape=(1, 1, 1, 64, 64))]

    plugin = DummyPlugin()
    assert plugin.name == "Dummy"
    assert len(plugin.test_cases()) == 1
