# Collaboration Notes

**Audience.** The next AI that picks up this project.

**Purpose.** Avoid the mistakes the previous AI (me, Opus 4.7) made.
The user has invested hours iterating; repeating known-bad patterns
will burn their patience.

---

## The user

Julio Maragall, `maragall@cephla.com`. Builds scientific software
for Cephla-Lab's Squid microscope. Has deep domain context on:

- Microscopy post-processing pipelines (flatfield, stitching,
  deconvolution, phase retrieval, denoising, segmentation)
- Reference implementations: napari, Cephla-Lab's `ndviewer_light`,
  `image-stitcher`, `stitcher`/TileFusion, PetaKit5D, waveorder
- Commercial microscopy GUIs: NIS Elements (Nikon), Araceli Endeavor,
  Revvity Harmony. Pulls UX patterns from all three.
- AOSA book (Architecture of Open Source Applications). Wants formal
  architecture, not improvisation.

He is honest about what he wants and does not hide frustration. He
will say "you shortcut because of the friction I'm giving you" and he
means it. He will also say "HAHAHA" when the result is visibly wrong
— take that as feedback, not ridicule.

## Hard rules

### 1. Ground every change in existing code

Every change must point to a `file:line` in the current repo. If you
propose something, say which file(s) you'll touch and why. If the
user asks "why X?" answer with a code location.

**Bad:** "I'll add a RangeSlider widget because napari uses one."
**Good:** "widget.py:_build_channel_checkboxes creates min_slider (col
1) and max_slider (col 2). To get one slider per row, drop the
min_slider add, keep the widget as a hidden object so
_on_contrast_changed's tick-reading code keeps working. Touches
widget.py only."

### 2. Port, don't reinvent

The audit at `references/audits/2026-04-21-reinvention-audit.md`
catalogs ~26 components vs the `_audit/` reference repos. 15% of our
code is reinvention (some justified, some not). The user's strongest
heuristic: "I have invented nothing with this software solution."
Meaning: check `_audit/` FIRST before writing anything.

**Where to look for reference patterns:**
- Channel composite + colormaps → `_audit/ndviewer_light/ndviewer_light/core.py` (napari layer mode)
- Contrast limits → `_audit/image-stitcher/hcs_viewer/grid_viewer_gui.py`
- Stitcher defaults → `_audit/stitcher/src/tilefusion/core.py:85-115`
- GUI parameter manifests → the absorbed plugin's source GUI file
- Plane/tile caching → `_audit/ndviewer_light/ndviewer_light/core.py`

### 3. No hardcoded values in plugins

- Pixel size, NA, wavelength, z-step → from `acquisition.optical` /
  `acquisition.objective` / `acquisition.channels`.
- `Acquisition.model_post_init` in `core/data_model.py` cross-
  populates `.optical` from `.objective` so every reader produces the
  same shape. Plugins call `plugin.default_params(acq.optical)`.
- If a plugin can't compute a default from metadata, it should RAISE
  (see `StitcherParams` / `DeconvolutionParams`), not silently fall
  back to a fiction.

### 4. No bloat

- Adding a new runtime dep needs a one-line justification. User
  explicitly rejected `superqt` (range slider) as bloat.
- Skill scope is one skill per concern. Don't invent processes.
- Docs live where they're already living (`docs/superpowers/specs/`,
  `docs/superpowers/plans/`). Don't spawn new top-level dirs unless
  the user asks.

### 5. Don't loop on SIGABRT

I burned an hour of real time re-running pytest after Qt thread
teardowns caused `Fatal Python error: Aborted`. The user called it
out: "you crash python for an hour and don't notice." Rules now:
- Max 2 pytest runs per cycle (baseline + post-change).
- If the second run SIGABRTs, parse the output (which test
  function fires the abort), don't re-run blindly.
- For Qt threads, the `AsyncTileLoader._async_default = False` flag
  in `tests/conftest.py` makes tests use synchronous mode. Any new
  QThread-based widget must have the same off-switch for tests.

### 6. Finish before starting

When the user says "converge v1", they mean CLOSE items on the list
— not open new ones. Don't start a new architectural direction
mid-convergence.

### 7. Small batches, grounded, no shortcuts

The user's exact words: "Small batches. One concern at a time → one
fix → one verify." Don't bundle six fixes into one commit; if the
user tests and hits one problem, they can't tell which fix broke it.

Also: "don't shortcut because of the friction I'm giving you." If a
fix has multiple parts, do them all properly — don't land a half
version to move on.

### 8. GUI pattern sources

When designing GUI, compare against:
- **NIS Elements** — right-click contextual menus, double-click
  nested menus, ribbon-style tab grouping, no deep menu nesting.
- **Araceli Endeavor** — wizard / step-based pipeline flows, linear
  pipeline metaphor.
- **Revvity Harmony** — drag-pipeline builder, heatmap well plate
  grid, hover previews, top-toolbar mode switching.

If you're not sure whether a GUI decision is right, ask which of the
three the user is mentally comparing against.

### 9. Screenshots are evidence

When the user tests and gives feedback, they're usually looking at a
screenshot. They will describe what they see. Trust the description;
don't argue with geometry.

### 10. AOSA Eclipse RCP is the formal architecture

The reinvention audit identified Eclipse RCP's plugin architecture
as the closest AOSA fit. Five invariants:
1. Plugin = self-contained package (no cross-plugin imports)
2. Registry = single source of truth
3. Extension points = formal hooks for v2
4. Stateless service interfaces
5. Declarative configuration over code (manifests)

Check any proposed change against these five.

---

## How the user iterates

A typical test cycle:

1. User launches `python -m squid_tools ~/Downloads/10x_mouse_brain…`
2. App runs against a 70-FOV 4-channel 10x mouse brain acquisition
3. User reports: screenshot observation + log paste + one or two
   asks
4. AI grounds each ask in a file:line and proposes the minimum fix
5. AI commits, user relaunches

Common feedback types (rank by frequency):

- **GUI geometry**: "canvas isn't centered", "left column too wide",
  "two columns of sliders", "processing tabs eat the viewer"
- **Log noise**: recurring stack traces → indicates a silent
  regression the AI didn't catch
- **Semantic correctness**: "stitcher defaults don't match the
  reference", "auto-contrast fails", "sidecar isn't populated"
- **Abstraction**: "umbrella terms should match field usage",
  "hardcoded values", "this is a scale concern not a correctness one"

The user will rarely give you the root cause directly. They will
describe the symptom and leave root-cause analysis to you.

---

## My failure modes (don't repeat)

Catalogued for honesty:

1. **Loop on SIGABRT.** Re-ran pytest three times after the same
   Qt-thread teardown crash without parsing the output. Cost: ~1 hour
   of user patience. Fix: read the crash output before retrying.

2. **Reinvent the compositor.** Wrote a CPU additive-blend compositor
   when `ndviewer_light`'s napari composite mode was the reference.
   User said "you've confidently reinvented the wheel." Fix: check
   `_audit/` BEFORE writing.

3. **Hardcoded pixel size = 0.325.** Plugin defaulted to a Cephla
   10x pixel size. User said "there shouldn't be hardcoded values
   in general." Fix: require metadata, raise if absent.

4. **Squared the wrong widget.** Made the whole `ViewerWidget`
   square, so the canvas (a child) was still rectangular. User's
   reply: "HAHAHA". Fix: be precise about which widget gets the
   constraint.

5. **Too-wide left column.** 260 px fixed width on both sides. User
   said "takes too much space." Fix: use setMaximumWidth +
   setMinimumWidth(0) + setChildrenCollapsible(True).

6. **Audit agent got stitcher wrong.** Claimed no global opt; actually
   `two_round_optimization` is called in `run_live`. Fix: always
   verify audit-agent claims with a grep before relaying.

7. **New specs before finishing existing ones.** Spec'd Cycle B-G
   while Cycle A had loose ends. User called this "scope creep into
   v1". Fix: finish current cycle before spec'ing the next.

8. **Tab labels were too long.** "Flatfield Correction" vs "Flatfield
   (BaSiC)". Eventually settled: umbrella categories are tab titles;
   algorithm names are in the toggle text or tab suffix (if multiple
   algos per category).

---

## How to signal progress

When you land a change, respond with:
1. What you changed (file:line or files touched).
2. What you grounded against (reference repo path or existing code).
3. Tests passing count + ruff status.
4. What's next (or "done, waiting for feedback").

Don't narrate the journey. The user has limited patience for
meta-commentary.

---

## Process conventions in the repo

- **Specs** live at `docs/superpowers/specs/YYYY-MM-DD-name.md`
- **Plans** live at `docs/superpowers/plans/YYYY-MM-DD-name.md`
- **Audits** live at `docs/superpowers/audits/YYYY-MM-DD-name.md`
- **Testing Plan section in specs is a placeholder.** Per the user's
  memory note: per-cycle TDD tests live in the plan; the spec's
  testing plan is end-of-product and gets filled in when v1 is done.
- **Commit messages** use conventional `feat|fix|docs|test|chore|
  style|refactor(scope): subject` with body explaining WHY, and a
  `Co-Authored-By: Claude Opus 4.7 (1M context)` trailer.
- **Cycles** get letters (B, C, D… A was the pre-v1 selection+live).
- **`_audit/`** is git-ignored; reference repos only.
- **`.worktrees/`** for isolated feature branches; git-ignored.
