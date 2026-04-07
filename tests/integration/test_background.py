import dask.array as da
import numpy as np

from squid_tools.plugins.background import BackgroundParams, BackgroundPlugin


def test_background_plugin_attributes():
    plugin = BackgroundPlugin()
    assert plugin.name == "Background Subtraction"
    assert plugin.category == "correction"
    assert plugin.requires_gpu is False


def test_background_plugin_parameters():
    plugin = BackgroundPlugin()
    assert plugin.parameters() is BackgroundParams


def test_background_plugin_default_params():
    plugin = BackgroundPlugin()
    params = plugin.default_params(None)
    assert isinstance(params, BackgroundParams)


def test_background_plugin_process():
    plugin = BackgroundPlugin()
    params = BackgroundParams()
    img = np.zeros((1, 1, 1, 64, 64), dtype=np.float64)
    img[:, :, :, :, :] = 100.0
    img[:, :, :, 20:40, 20:40] = 500.0
    frames = da.from_array(img)
    result = plugin.process(frames, params).compute()
    assert result[0, 0, 0, 30, 30] > result[0, 0, 0, 5, 5]


def test_background_plugin_test_cases():
    plugin = BackgroundPlugin()
    cases = plugin.test_cases()
    assert len(cases) >= 1
