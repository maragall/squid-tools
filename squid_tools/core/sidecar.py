"""OME sidecar: non-destructive output alongside Squid acquisitions.

Processing results are stored in .squid-tools/ within the acquisition
directory. Original files are never modified. The manifest.json tracks
what was run, when, and with what parameters.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ProcessingRun(BaseModel):
    """Record of a single processing operation."""

    plugin: str
    version: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    params: dict[str, Any] = {}
    input_hash: str | None = None
    output_path: str = ""


class SidecarManifest(BaseModel):
    """Manifest tracking all processing runs for an acquisition."""

    acquisition_path: Path
    runs: list[ProcessingRun] = []

    model_config = {"arbitrary_types_allowed": True}

    def add_run(self, run: ProcessingRun) -> None:
        """Record a processing run."""
        self.runs.append(run)

    def save(self) -> None:
        """Write manifest to .squid-tools/manifest.json."""
        sidecar_dir = self.acquisition_path / ".squid-tools"
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = sidecar_dir / "manifest.json"

        data = {
            "runs": [run.model_dump() for run in self.runs],
        }
        with open(manifest_path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, acquisition_path: Path) -> SidecarManifest:
        """Load manifest from .squid-tools/manifest.json."""
        manifest_path = acquisition_path / ".squid-tools" / "manifest.json"
        manifest = cls(acquisition_path=acquisition_path)

        if manifest_path.exists():
            with open(manifest_path) as f:
                data = json.load(f)
            manifest.runs = [ProcessingRun(**r) for r in data.get("runs", [])]

        return manifest

    def plugin_output_dir(self, plugin_name: str) -> Path:
        """Get or create the output directory for a plugin."""
        out_dir = self.acquisition_path / ".squid-tools" / plugin_name
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir
