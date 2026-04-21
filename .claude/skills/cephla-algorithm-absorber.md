# Cephla Post-Processing Algorithm Absorber

## Purpose

Absorb an external microscopy algorithm repository into squid-tools as a processing module. The agent follows a strict 9-step protocol to strip IO, strip GUI, wrap the algorithm in the ProcessingPlugin ABC, write tests, and verify in dev mode.

**When to use:** When told to "absorb", "integrate", "add", or "wrap" an external repository into squid-tools' processing/ directory.

**Announce at start:** "I'm using the Cephla Algorithm Absorber skill to integrate this repository."

## Prerequisites

Before starting, verify:
1. The squid-tools repo is cloned and the core library works (`pytest` passes)
2. The source repository is accessible (cloned locally or available via git)
3. You understand what the algorithm does (read its README)

## The Protocol

### Step 1: Audit the Source Repository

Clone or read the source repo. Identify:
- **Algorithm code:** The actual computation (registration, deconvolution, phase retrieval, etc.)
- **IO code:** File readers, writers, format parsers (WILL BE DROPPED)
- **GUI code:** Any Qt/tkinter/napari widgets (WILL BE DROPPED)
- **Dependencies:** What the algorithm needs (numpy, scipy, numba, cupy, etc.)
- **Tests:** What tests exist in the source repo

Report what you found. List files in three categories: ABSORB, DROP, REFACTOR.

### Step 2: Create the Processing Module

Create the directory structure:

```
squid_tools/processing/{name}/
├── __init__.py          # exports the plugin class
├── plugin.py            # ProcessingPlugin implementation
└── {algorithm}.py       # Algorithm code (one or more files)
```

If the source repo has clean file separation (e.g., registration.py, fusion.py, optimization.py), keep that separation. Don't flatten what's already modular. Don't split what's naturally one thing.

### Step 3: Copy Algorithm Code

Copy the pure algorithm files into the processing module. For each file:

**DO:**
- Keep the original docstrings and comments
- Keep the original function signatures (they're the proven API)
- Update relative imports to match the new package location
- Keep GPU/CPU abstractions (try/except cupy pattern)

**DO NOT:**
- Copy any file-reading code (os.path, open(), tifffile.imread from paths)
- Copy any file-writing code (tifffile.imwrite, zarr store creation)
- Copy any GUI code (Qt imports, matplotlib, napari)
- Copy any CLI code (argparse, click)
- Add new features or refactor the algorithm

### Step 4: Write the Plugin Wrapper

Create `plugin.py` implementing `ProcessingPlugin`:

```python
from squid_tools.processing.base import ProcessingPlugin

class {Name}Plugin(ProcessingPlugin):
    name = "{Human Readable Name}"    # Shown in GUI tab
    category = "{category}"            # stitching, correction, deconvolution, phase
    requires_gpu = False               # True if GPU is mandatory (not optional)

    def parameters(self) -> type[BaseModel]:
        """Return Pydantic model with ALL tunable parameters.
        Defaults must be sensible for typical microscopy data."""
        return {Name}Params

    def validate(self, acq: Acquisition) -> list[str]:
        """Check data compatibility. Return warnings, not errors.
        E.g., 'Deconvolution works best with z-stacks (this is 2D)'"""
        ...

    def process(self, frames: np.ndarray, params: BaseModel) -> np.ndarray:
        """Single-frame processing. Numpy in, numpy out.
        For spatial plugins, this is a passthrough."""
        ...

    def process_region(self, frames, positions, params) -> np.ndarray | None:
        """Override ONLY for spatial plugins (stitching, mosaic ops).
        Return None if this plugin is not spatial."""
        return None

    def default_params(self, optical: OpticalMetadata) -> BaseModel:
        """Auto-populate from metadata. The user should never need to
        type a number they don't understand."""
        ...

    def test_cases(self) -> list[dict]:
        """Synthetic input/expected output. These run automatically.
        Test pixel VALUES, not just shapes."""
        ...
```

### Step 4.5: Capture the Source GUI's Parameter Manifest

An algorithm's source repo usually ships a GUI (Qt, Streamlit, napari-plugin, whatever). That GUI encodes years of scientific wisdom: which parameters are sensible defaults, which are exposed to users, what tooltips explain, what min/max guard against. DO NOT discard this knowledge.

Write `processing/{name}/gui_manifest.yaml` alongside `plugin.py`:

```yaml
name: {PluginName}
source_repo: https://github.com/owner/repo
source_gui: path/inside/source_repo/to/the_gui.py
notes: |
  One or two sentences on why the defaults are what they are
  (e.g. "Defaults tuned for Cephla 10x / 0.752 µm pixel size",
  "Downsample factor 4 was the sweet spot in the source repo's
  stitcher_gui.py comments").

parameters:
  pixel_size_um:
    default: 0.752
    visible: true
    tooltip: "Native pixel size (µm)."
    min: 0.01
    max: 100.0
    step: 0.01
  internal_tuning_constant:
    default: 15
    visible: false   # never shown to end users; set by the source GUI
```

Rules:

1. Look at the source GUI file and for each widget backing a parameter, record:
   - Its default value (from the widget's initial state or a constant).
   - Its tooltip / label text (copy verbatim, don't paraphrase).
   - Its min/max/step if the widget is bounded.
2. If the source GUI does NOT expose a parameter but the algorithm accepts it, mark `visible: false` and include the default. Users won't see it; calls still use the right value.
3. The `notes` field captures any context from the source repo's README, inline comments, or the gui file about why defaults were chosen. This is where to paste the tl;dr that future readers need.
4. Don't invent parameters the source GUI doesn't have. If the source GUI exposes a parameter you don't see in your plugin's Pydantic model, that's a plugin-wrapper bug — go back to Step 4.

`ProcessingTabs` auto-consumes this manifest. No GUI code to write.

### Step 5: Strip IO

The algorithm must NOT read or write files. It receives numpy arrays from squid-tools' core/readers via the plugin ABC.

Search the copied code for these patterns and REMOVE them:
- `open(`, `Path(`, `os.path`
- `tifffile.imread`, `tifffile.imwrite`
- `zarr.open`, `zarr.DirectoryStore`
- `csv.reader`, `yaml.safe_load`
- Any path string manipulation

Replace with: function parameters that accept numpy arrays directly.

### Step 6: Declare Dependencies

Create `processing/{name}/pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "squid-tools-{name}"
version = "0.1.0"
description = "{description}"
requires-python = ">=3.10"
dependencies = [
    "squid-tools-core>=0.1.0",
    # ONLY what the algorithm needs. No GUI deps. No reader deps.
]

[project.entry-points."squid_tools.plugins"]
{name} = "squid_tools.processing.{name}.plugin:{Name}Plugin"
```

Add the entry point to the root `pyproject.toml` as well.
Add algorithm-specific deps to root `pyproject.toml` dependencies list.
Run `pip install -e ".[dev]"`.

### Step 7: Write Tests

Write tests that verify:

1. **Plugin instantiation:** name, category, requires_gpu are correct
2. **Parameters:** parameters() returns the Pydantic model class
3. **Validation:** validate() returns empty list for valid data
4. **Processing:** process() transforms data correctly (test pixel VALUES)
5. **Default params:** default_params() auto-populates from metadata
6. **Test cases:** test_cases() returns non-empty list
7. **Algorithm-specific:** At least 2 tests that verify the algorithm works correctly on synthetic data

For spatial plugins, also test:
8. **process_region():** returns a fused/assembled result from multiple tiles

Every test follows TDD: write test, verify FAIL, implement/fix, verify PASS.

### Step 8: Memory Safety Check

Verify the absorbed code meets memory safety standards:

- [ ] Never holds more than one frame in memory at a time (unless the algorithm requires it)
- [ ] Accepts and returns numpy arrays (not file handles, not paths)
- [ ] Does not allocate GPU memory without `try: import cupy` pattern
- [ ] Does not spawn threads or processes without cleanup
- [ ] No `eval()`, `exec()`, `subprocess`, or network access

If any check fails, fix the code.

### Step 9: Verify and Register

1. Run: `ruff check squid_tools/processing/{name}/`
2. Run: `mypy squid_tools/processing/{name}/` (if feasible)
3. Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/test_{name}*.py -v`
4. Register in `squid_tools/gui/app.py` `_register_default_plugins()`
5. Run full test suite: `QT_QPA_PLATFORM=offscreen pytest -v --tb=short`
6. Verify in dev mode: `QT_QPA_PLATFORM=offscreen python -m squid_tools --dev`
7. Commit everything

## Quality Gate

The absorbed module ships ONLY if ALL of the following pass:
- All tests pass (including test_cases() from the plugin)
- ruff clean
- No file IO in the algorithm code
- No GUI imports in the algorithm code
- Memory safety checklist complete
- Plugin registered and visible in processing tabs

If any gate fails, fix before merging. An agent that cannot meet these standards should not merge the module.

## Example: Absorbing a Deconvolution Repo

```
Input: "Absorb maragall/Deconvolution into squid-tools"

Step 1: Audit
  ABSORB: engine.py (Richardson-Lucy, OMW), psf.py (PSF generation)
  DROP: io/ (file readers), gui/ (Qt viewer), cli.py (argparse)
  Dependencies: cupy (optional), scipy, psfmodels

Step 2: Create processing/deconvolution/
Step 3: Copy engine.py, psf.py (strip file paths)
Step 4: Write DeconPlugin with DeconParams(iterations, method, regularization)
Step 5: Remove all tifffile.imread calls, accept np.ndarray
Step 6: pyproject.toml with scipy, psfmodels deps
Step 7: 8 tests (instantiation, params, RL on synthetic bead, OMW on synthetic)
Step 8: Memory check (GPU allocation uses try/except cupy, cleanup in finally)
Step 9: Register, verify, commit

Output: processing/deconvolution/ with ~400 lines of algorithm + ~100 lines plugin wrapper
```

## Red Flags

**Never:**
- Copy IO code (even "temporarily")
- Copy GUI code
- Add dependencies that aren't needed by the algorithm
- Skip the memory safety check
- Ship without test_cases() passing
- Modify the ProcessingPlugin ABC to fit the algorithm (the algorithm adapts to the ABC, not the other way around)

**Always:**
- Read the source repo's README first
- Audit before copying
- Test pixel values, not just shapes
- Keep the source repo's proven file separation
- Run the full test suite before declaring done
