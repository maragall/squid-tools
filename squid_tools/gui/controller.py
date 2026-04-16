"""Application controller: mediates between GUI widgets and core library.

Owns the Acquisition, FormatReader, Pipeline, PluginRegistry, and
SidecarManifest. GUI widgets emit signals, the controller handles them.
All business logic lives here, not in widgets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from squid_tools.core.data_model import Acquisition, FrameKey
from squid_tools.core.pipeline import Pipeline
from squid_tools.core.readers import detect_reader
from squid_tools.core.readers.base import FormatReader
from squid_tools.core.registry import PluginRegistry
from squid_tools.core.sidecar import SidecarManifest
from squid_tools.viewer.data_manager import ViewportDataManager


class AppController:
    """Central controller for squid-tools.

    Manages data loading, frame retrieval, plugin execution, and sidecar output.
    GUI widgets call this controller; it calls the core library.
    """

    def __init__(self, registry: PluginRegistry | None = None) -> None:
        self.registry = registry or PluginRegistry()
        self.acquisition: Acquisition | None = None
        self.pipeline = Pipeline()
        self.sidecar: SidecarManifest | None = None
        self._reader: FormatReader | None = None
        self.data_manager = ViewportDataManager()

    def load_acquisition(self, path: Path) -> Acquisition:
        """Load an acquisition directory. Auto-detects format."""
        self._reader = detect_reader(path)
        self.acquisition = self._reader.read_metadata(path)
        self.sidecar = SidecarManifest(acquisition_path=path)
        self.data_manager.load(path)
        return self.acquisition

    def get_frame(
        self,
        region: str,
        fov: int,
        z: int = 0,
        channel: int = 0,
        timepoint: int = 0,
    ) -> np.ndarray:
        """Load a single frame."""
        if self._reader is None:
            raise RuntimeError("No acquisition loaded")
        key = FrameKey(region=region, fov=fov, z=z, channel=channel, timepoint=timepoint)
        return self._reader.read_frame(key)

    def get_region_frames(
        self,
        region: str,
        z: int = 0,
        channel: int = 0,
        timepoint: int = 0,
    ) -> dict[int, np.ndarray]:
        """Load all FOV frames for a region. Returns {fov_index: frame}."""
        if self._reader is None or self.acquisition is None:
            raise RuntimeError("No acquisition loaded")
        if region not in self.acquisition.regions:
            raise ValueError(f"Region '{region}' not found")

        frames: dict[int, np.ndarray] = {}
        for fov in self.acquisition.regions[region].fovs:
            key = FrameKey(
                region=region, fov=fov.fov_index, z=z, channel=channel, timepoint=timepoint
            )
            frames[fov.fov_index] = self._reader.read_frame(key)
        return frames

    def run_plugin(
        self,
        plugin_name: str,
        frame: np.ndarray,
        params: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Run a plugin on a frame. Returns processed frame."""
        plugin = self.registry.get(plugin_name)
        if plugin is None:
            raise ValueError(f"Plugin '{plugin_name}' not found")

        params_model_cls = plugin.parameters()
        if params:
            params_model = params_model_cls(**params)
        else:
            optical = self.acquisition.optical if self.acquisition else None
            params_model = plugin.default_params(optical)

        return plugin.process(frame, params_model)
