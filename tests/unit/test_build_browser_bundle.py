"""Test that the build_browser_bundle script produces a coherent bundle."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_build_bundle_end_to_end(
    tmp_path: Path, individual_acquisition: Path,
) -> None:
    repo_root = Path(__file__).parent.parent.parent
    bundle = tmp_path / "bundle"
    script = repo_root / "scripts" / "build_browser_bundle.py"
    cmd = [
        sys.executable,
        str(script),
        "--path", str(individual_acquisition),
        "--region", "0",
        "--channel", "0",
        "--output", str(bundle),
    ]
    env = dict(os.environ, PYTHONPATH=str(repo_root))
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=120, env=env,
    )
    assert result.returncode == 0, (
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert (bundle / "viewer.html").is_file()
    manifest_path = bundle / "tiles.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text())
    assert "bounds" in manifest
    assert "tiles" in manifest
    assert len(manifest["tiles"]) > 0
    first = manifest["tiles"][0]
    tile_file = bundle / Path(first["url"]).name
    assert tile_file.is_file()
