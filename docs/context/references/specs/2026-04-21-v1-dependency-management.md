# v1 Dependency Management + Customer Module Installer

## Purpose

Users install squid-tools with the processing modules they need, not all of them. A microscopy lab that only stitches shouldn't carry deconvolution's CUDA wheels. A web demo shouldn't ship BaSiCPy. This document lays out how v1 packages its plugins so users (humans or agents) can compose installations at runtime, and how a customer-facing installer gives a researcher checkboxes instead of pip syntax.

**Audience:** Anyone adding or absorbing a plugin. Whoever operates the download site. The customer-facing installer UI.

**Guiding principle:** Every plugin is its own namespace package, its own pyproject.toml, its own optional extra. The core ships thin; everything else is opt-in.

---

## Current state

```toml
# squid_tools/pyproject.toml (today, simplified)
[project]
dependencies = [
  "pydantic>=2.10", "numpy", "dask", "tifffile", "pyyaml", "zarr",
  "PySide6", "vispy", "scikit-image", "scipy", "numba",
  "sep", "boto3", "psfmodels",  # etc etc
]
```

Flat list. Adding aCNS pulled scikit-image. Adding decon pulled scipy + scikit-image. Adding R2 pulled boto3. All required, whether the user touches them or not.

Also: every processing package (`squid_tools/processing/{flatfield,stitching,decon,phase,acns,bgsub}`) has its own `pyproject.toml`, but the top-level meta-package lists them all as required — so the namespace-package isolation isn't actually used.

---

## Proposed layout

### A. Each plugin is an optional extra on the meta-package

```toml
# squid_tools/pyproject.toml  — meta-package
[project]
name = "squid-tools"
dependencies = [
  # CORE ONLY — everything every user needs
  "squid-tools-core",
  "squid-tools-viewer",
  "squid-tools-app",
]

[project.optional-dependencies]
stitching     = ["squid-tools-stitching"]
flatfield     = ["squid-tools-flatfield"]
decon         = ["squid-tools-decon"]
phase         = ["squid-tools-phase"]
denoising     = ["squid-tools-denoising"]
bgsub         = ["squid-tools-bgsub"]
r2            = ["squid-tools-remote-r2"]
3d            = ["squid-tools-viewer-3d"]

# Convenience bundles
all-corrections   = ["squid-tools[flatfield,denoising,bgsub]"]
all-restoration   = ["squid-tools[decon,phase,denoising]"]
everything        = [
  "squid-tools[stitching,flatfield,decon,phase,denoising,bgsub,r2,3d]",
]
```

User installs:
```bash
pip install squid-tools[stitching,flatfield]      # minimal
pip install squid-tools[everything]               # firehose
pip install squid-tools[all-restoration,r2]       # composed bundle
```

### B. Each plugin sub-package declares its OWN deps

```toml
# processing/decon/pyproject.toml
[project]
name = "squid-tools-decon"
dependencies = [
  "squid-tools-core",
  "numpy",
  "scipy",
  "scikit-image",
  "psfmodels",
]
[project.optional-dependencies]
gpu = ["cupy-cuda12x"]   # opt-in GPU acceleration

[project.entry-points."squid_tools.plugins"]
decon = "squid_tools.processing.decon.plugin:DeconvolutionPlugin"
```

Plugin's `gui_manifest.yaml` stays next to `plugin.py` — already implemented in Cycle J.

### C. Plugins are discovered at runtime via entry points

`squid_tools/core/registry.py` already does this (pre-v1). The runtime lists every entry point registered under `squid_tools.plugins`, attempts to load it, and skips any that fail to import (module not installed → silent skip). The GUI only shows tabs for plugins whose imports succeed.

### D. Versioning

Each sub-package gets independent version bumps. Breaking changes to `squid-tools-core` bump the major; plugin packages pin a compatible range: `"squid-tools-core>=1.2,<2.0"`. PyPI ranges do the rest.

---

## Customer installer (GUI)

### User story

A life-sciences researcher downloads `squid-tools-installer.exe` / `.AppImage`. They double-click. A wizard shows:

```
Welcome to Squid-Tools.

Which post-processing modules do you need?

  [ ] Stitching              — align tiles, fuse overlaps
  [ ] Flatfield Correction   — illumination flattening (BaSiCPy)
  [ ] Deconvolution          — Richardson-Lucy with objective PSF
  [ ] Phase from Defocus     — quantitative phase retrieval (waveorder)
  [ ] Denoising              — analytical (aCNS) + BM3D (when available)
  [ ] Background Subtraction — sep.Background
  [ ] GPU acceleration       — CuPy (NVIDIA only, adds ~1 GB)
  [ ] 3D volume viewer       — z-stack ray marching
  [ ] Cloud demo (R2)        — upload acquisitions for web viewing

Estimated install size: 340 MB   [Install]   [Skip all — thin install]
```

Clicking Install runs `pip install squid-tools[<selected_extras>]` into a sandboxed Python shipped with the installer. Success dialog → launcher shortcut.

### Implementation

**Two pieces.**

#### 1. `squid_tools_installer/` — the installer app itself

Separate tiny repo (or `installer/` subdir). PySide6 window, one QListWidget with checkboxes, reads a `modules.json` manifest listing every extra + description + size + deps. On install, shells out to the bundled Python:

```python
subprocess.run([
    bundled_python, "-m", "pip", "install",
    "--index-url", "https://cephla-downloads.r2.cloudflarestorage.com/simple/",
    f"squid-tools[{','.join(selected)}]",
])
```

Size estimate comes from a pre-computed `modules.json` that CI updates on every release.

#### 2. `modules.json` on the download CDN

```json
{
  "version": "1.0.0",
  "modules": {
    "stitching": {
      "label": "Stitching",
      "blurb": "Align tiles, fuse overlaps",
      "size_mb": 55,
      "deps": ["numba", "scikit-image"]
    },
    "decon": { ... },
    ...
  }
}
```

Served from R2 via Cloudflare Pages. CI builds each release, uploads wheels to R2's pip-index layout, and refreshes `modules.json` with sizes.

### Why not one-big-installer

- **Smaller downloads**: nobody grabs 1 GB of CUDA wheels if they're not using GPU.
- **Clearer trust story**: user sees what the app is going to install, doesn't pip-pull 100 transitive deps.
- **Faster updates**: a deconvolution patch doesn't make every user re-download the whole stack.
- **Agentic absorption fits naturally**: the absorber skill writes a new plugin package and a corresponding installer-manifest entry.

---

## What changes in v1

| Change | Scope |
|---|---|
| Split `squid_tools/pyproject.toml` dependencies into core + optional extras | 1 file edit |
| Verify each `processing/{name}/pyproject.toml` lists only its own deps | 6 files, audit |
| Add `modules.json` generator script | new `scripts/build_installer_manifest.py` |
| Installer app scaffolding | new `squid_tools_installer/` (PySide6 window) |
| CI: per-push, rebuild + publish wheels + refresh `modules.json` | `.github/workflows/release.yml` |

Scope for v1: items 1–3 (packaging). The installer-GUI (item 4) ships in v2 A2.

---

## Open questions

- **Wheels for CuPy on macOS**: CuPy's CUDA wheels don't exist on macOS. Plan: the `gpu` extra is Linux/Windows-only; on macOS the installer hides the checkbox.
- **`ndviewer_light` dep on the 3D path**: do we depend on its package, or vendor the parts we use? Leaning vendor — the repo layout encourages drop-in absorption.
- **Download index hosting**: R2 as a static pip index works (tested), but pip's `--index-url` must serve `/simple/` correctly. CI needs to generate those files.

---

## Not in scope (v2 A-series)

- The actual installer GUI (A2) — this doc scaffolds it.
- CI wheel publishing to R2 (F1) — this doc spells the contract.
- Checkbox-interview UX polish — usability pass after first customer trial.

---

## Testing plan

_(Project convention: functional plan lives at the end of the final product spec. Per-cycle TDD goes in the plan.)_

What we test for the v1 packaging changes:

- `pip install squid-tools` (no extras) → core + viewer + app import cleanly; `registry.list_all()` returns only plugins whose package imports succeed.
- `pip install squid-tools[stitching]` → Stitcher plugin appears in `list_all()`; Flatfield does not.
- Every processing/*/pyproject.toml's `dependencies` list is a strict subset of its actual imports (`scripts/audit_deps.py`).
- `modules.json` is valid JSON and references every extra declared in the meta-pyproject.
