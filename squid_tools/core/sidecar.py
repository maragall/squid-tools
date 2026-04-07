from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class ProcessingRun(BaseModel):
    plugin: str
    version: str
    params: dict[str, Any]
    output_path: str
    timestamp: str = ""
    input_hash: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class SidecarManager:
    def __init__(self, acquisition_path: Path) -> None:
        self._acq_path = acquisition_path
        self._sidecar_path = acquisition_path / ".squid-tools"
        self._manifest_path = self._sidecar_path / "manifest.json"

    def ensure_directory(self) -> None:
        self._sidecar_path.mkdir(exist_ok=True)
        if not self._manifest_path.exists():
            self._write_manifest({"runs": []})

    def record_run(self, run: ProcessingRun) -> None:
        manifest = self.load_manifest()
        manifest["runs"].append(run.model_dump())
        self._write_manifest(manifest)

    def load_manifest(self) -> dict[str, Any]:
        if not self._manifest_path.exists():
            return {"runs": []}
        with open(self._manifest_path) as f:
            return json.load(f)

    def plugin_output_dir(self, plugin_name: str) -> Path:
        out_dir = self._sidecar_path / plugin_name
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        self._sidecar_path.mkdir(exist_ok=True)
        with open(self._manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
