import dask.array as da
import numpy as np

from squid_tools.plugins.flatfield import FlatfieldParams, FlatfieldPlugin


def test_flatfield_plugin_attributes():
    plugin = FlatfieldPlugin()
    assert plugin.name == "Flatfield Correction"
    assert plugin.category == "correction"


def test_flatfield_plugin_process():
    plugin = FlatfieldPlugin()
    params = FlatfieldParams()
    y, x = np.mgrid[0:64, 0:64]
    illumination = 1.0 + 0.3 * np.sin(x * np.pi / 64)
    signal = np.ones((64, 64), dtype=np.float64) * 1000
    img = (signal * illumination).reshape(1, 1, 1, 64, 64)
    frames = da.from_array(img)
    result = plugin.process(frames, params).compute()
    original_std = np.std(img[0, 0, 0])
    corrected_std = np.std(result[0, 0, 0])
    assert corrected_std < original_std


def test_flatfield_plugin_test_cases():
    plugin = FlatfieldPlugin()
    assert len(plugin.test_cases()) >= 1
