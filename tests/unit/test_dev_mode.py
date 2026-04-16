"""Tests for dev mode plugin hot-loading."""

import textwrap
from pathlib import Path

from squid_tools.gui.dev_panel import load_plugin_from_file


class TestDevMode:
    def test_load_plugin_from_file(self, tmp_path: Path) -> None:
        plugin_code = textwrap.dedent("""
            import numpy as np
            from pydantic import BaseModel
            from squid_tools.processing.base import ProcessingPlugin
            from squid_tools.core.data_model import Acquisition, OpticalMetadata

            class TestParams(BaseModel):
                value: float = 1.0

            class MyPlugin(ProcessingPlugin):
                name = "DevTest"
                category = "correction"
                requires_gpu = False

                def parameters(self):
                    return TestParams

                def validate(self, acq):
                    return []

                def process(self, frames, params):
                    return frames + params.value

                def default_params(self, optical=None):
                    return TestParams()

                def test_cases(self):
                    return [{"input": np.ones((10, 10)), "expected": np.ones((10, 10)) + 1}]
        """)
        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text(plugin_code)

        plugins = load_plugin_from_file(plugin_file)
        assert len(plugins) == 1
        assert plugins[0].name == "DevTest"

    def test_load_returns_empty_for_no_plugins(self, tmp_path: Path) -> None:
        code = "x = 1\n"
        f = tmp_path / "empty.py"
        f.write_text(code)
        plugins = load_plugin_from_file(f)
        assert len(plugins) == 0

    def test_load_bad_file_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("this is not valid python }{}{")
        plugins = load_plugin_from_file(f)
        assert len(plugins) == 0

    def test_plugin_process_works(self, tmp_path: Path) -> None:
        import numpy as np

        plugin_code = textwrap.dedent("""
            import numpy as np
            from pydantic import BaseModel
            from squid_tools.processing.base import ProcessingPlugin
            from squid_tools.core.data_model import Acquisition, OpticalMetadata

            class P(BaseModel):
                scale: float = 2.0

            class ScalePlugin(ProcessingPlugin):
                name = "Scale"
                category = "correction"

                def parameters(self):
                    return P

                def validate(self, acq):
                    return []

                def process(self, frames, params):
                    return frames * params.scale

                def default_params(self, optical=None):
                    return P()

                def test_cases(self):
                    return []
        """)
        f = tmp_path / "scale.py"
        f.write_text(plugin_code)

        plugins = load_plugin_from_file(f)
        result = plugins[0].process(np.ones((5, 5)), plugins[0].default_params())
        assert np.all(result == 2.0)
