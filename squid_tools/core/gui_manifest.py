"""GUI manifest loader for absorbed processing plugins.

Each plugin can ship a `gui_manifest.yaml` next to its `plugin.py` that
tells ProcessingTabs how to present the plugin to users:
- Which parameters to show vs. hide (expose scientific-wisdom defaults
  the source repo's GUI chose, without cluttering the user's view).
- Per-parameter tooltip, min/max range, and step.
- A "notes" block explaining why the defaults are what they are.

If no manifest is present, ProcessingTabs falls back to its previous
behavior: show every field from the plugin's Pydantic params class.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class GuiParameter(BaseModel):
    """Per-parameter GUI hint."""

    default: Any = None
    visible: bool = True
    tooltip: str = ""
    min: float | None = None
    max: float | None = None
    step: float | None = None


class GuiManifest(BaseModel):
    """Top-level manifest for a plugin's GUI presentation."""

    name: str
    source_repo: str | None = None
    source_gui: str | None = None
    notes: str = ""
    parameters: dict[str, GuiParameter] = Field(default_factory=dict)


def manifest_path_for(plugin_module_file: str | Path) -> Path:
    """Return the expected manifest path for a plugin's module file."""
    return Path(plugin_module_file).parent / "gui_manifest.yaml"


def load_manifest(plugin_module_file: str | Path) -> GuiManifest | None:
    """Load gui_manifest.yaml next to plugin_module_file if present."""
    path = manifest_path_for(plugin_module_file)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        return None
    return GuiManifest.model_validate(raw)
