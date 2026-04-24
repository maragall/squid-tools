# Brainstorming Highlights

**Caveat.** These are reconstructed from commit messages, spec docs,
and my session memory. I do NOT have the user's raw prompts saved.
Treat this as the GIST, not a transcript. Where a single phrase is
in quotes, it's something the user said; everything else is my
paraphrase.

Organized thematically rather than chronologically.

---

## 1. Architectural posture

### "I have invented nothing with this software solution"

The most load-bearing line of the whole session. Everything squid-
tools does has a reference in the `_audit/` directory. The user's
heuristic: before writing anything, check which reference repo
already solved this.

**Implications the user drew out:**
- Absorbing an algorithm isn't just porting its Python. It's also
  porting the source repo's GUI conventions: which parameters are
  defaults, which are user-exposed, what tooltips say.
- Every absorption should capture this as metadata (→ birth of
  `gui_manifest.yaml` in Cycle J).
- When porting, avoid gratuitous restructuring. If `tilefusion/core.
  py` has registration.py, fusion.py, optimization.py as separate
  files, keep that separation.

### Formal architecture from AOSA

The user pointed at the Architecture of Open Source Applications
book and asked: which AOSA-documented pattern should squid-tools
adopt? Answer (from the audit): Eclipse RCP plugin architecture.
Five invariants in `01-collaboration-notes.md`.

### "Simplify and clean the codebase so that my reviewing can be
more efficient"

Late-session directive. The user was tired of me patching. They
wanted the codebase SHAPED so that review was easy — not a pile of
fixes. Implication: prefer small, obvious diffs over big clever
refactors.

---

## 2. GUI vision

### Commercial references the user pulls from

- **NIS Elements (Nikon)**: ribbon-style tabs, right-click
  contextual menus, double-click nested menus, no deep menu nesting.
- **Araceli Endeavor**: wizard / step-based linear pipeline
  metaphor. User interacts with the pipeline as a sequence of
  discrete stages.
- **Revvity Harmony**: drag-pipeline builder, well-plate grid with
  heatmap coloring, hover previews, top toolbar for mode switching.

### "The goal is to maximize the area of the square canvas"

Repeated feedback. The canvas is the centerpiece. Every other UI
element competes for space. Decisions:
- Side columns collapsible so canvas can take 100%.
- Processing tabs moved from top ribbon to LEFT column (vertical
  tabs) so they don't steal vertical height.
- `SquareContainer` custom QWidget: centers its child at
  `side = min(W, H)`. Grounded in `viewer/square_container.py`.
- Left column orientation tried horizontally (wide) then vertically
  (narrow), settled on `TabPosition.West`.

### "Why two columns of sliders?"

User asked this twice. Answer: per-channel min and max contrast
sliders side by side. Fix: single slider per channel (upper clim
only), lower clim pinned to auto-detected p1. "auto" button resets
both. Min slider kept as hidden object so the contrast pipeline
keeps working.

### "FOV borders off by default"

Cephla-blue tile borders on by default was noisy for the user.
Default flipped to False in `canvas.py` and `controls.py`. Toggle in
controls panel + right-click menu.

### "Enable {algorithm} in pipeline"

User found this copy confusing: "life-sciences users don't
understand 'pipeline'." Changed to "Apply {algorithm} to viewer" in
processing_tabs.py.

### Umbrella terms

"Umbrella terms have to be like they actually name them in the
field." Translation: tab titles should be what microscopists call
them, not what engineers call them. Current umbrellas:
Shading / Denoising / Background / Deconvolution / Phase /
Stitching. These should be challenged / refined when the user gives
testing feedback. Hypotheses:
- "Shading" vs "Illumination Correction" (image-stitcher uses
  latter)
- "Background" vs "Background Subtraction"
- "Phase" vs "Quantitative Phase"

---

## 3. Algorithm coverage + absorption loop

### The absorber is the product

The user explicitly said adding N algorithms should be a one-folder
operation. The value is the LOOP, not the individual algorithms.
Proof of the loop: absorb one algorithm, observe the absorber
catches its GUI decisions, review, merge.

### "The algorithm absorber skill is what holds the suite together"

(Paraphrase.) A new plugin should be one `pyproject.toml`, one
`plugin.py`, one `gui_manifest.yaml`, one entry point. Everything
else is the skill's job.

### 9-step absorption protocol (evolved to 10 after Cycle J)

Step 4.5 added mid-session: capture the source GUI's parameter
manifest. Before Step 4.5, the absorber shipped an algorithm but
dropped its scientific wisdom (defaults, tooltips, range
constraints).

### Live-processing pattern per algorithm category

From the v1 spec (`references/specs/2026-04-09-squid-tools-v1-design
.md`):

- **Shading correction**: calibrate phase + apply phase. Calibrate
  samples random tiles, apply uses the resulting profile.
- **Stitching**: pairwise phase + global opt phase + fusion phase.
  Tiles shift live as pairs register.
- **Deconvolution**: per-tile iterative. Tile-by-tile update.
- **Phase from defocus**: per-FOV z-stack. Requires volumetric
  input.
- **Denoising (aCNS)**: calibrate (dark frames) + apply. Same
  shape as flatfield.
- **Segmentation**: per-tile model inference. Overlays appear as
  tiles complete.
- **Tracking**: time-series, user picks a cell, track extends.
- **Detection**: per-tile. Boxes appear as tiles complete.
- **3D rendering**: z-stack as volume. GPU ray marching.

### "Many many iterations of feedback"

The user explicitly set expectations: v1 would not land in one
pass. They would iterate through many rounds of testing +
feedback. The AI's job is to ground each round in existing code
and make minimum-viable fixes.

---

## 4. Scale concerns

### Petabyte-scale is a real design constraint

Repeatedly mentioned. Implications:
- The compositor cannot be per-channel layers (that's N× memory
  and draw calls). Pre-composite to RGB on CPU. Keep. The tension
  is: pre-composite is less responsive to per-channel contrast
  tweaks, but scales. Dual-mode design deferred to v2.
- Multi-scale pyramid (Cycle D) is foundational.
- Async tile loader (Cycle C) is foundational.
- Spatial index must remain fast. Our grid-based index is O(1)
  lookup. R-tree is a v2 option for irregular scans.

### Agentic loops can add N algorithms

The user wants the absorber to scale: drop a repo in `_audit/`,
run the skill, merge. N × M algorithms × suites. Each absorption
should be reviewed by a code-review agent before merging. The
three-node dev-absorb-demo network in the v1 spec captures this.

---

## 5. Dependency management

### "Scalable way to handle dependencies"

The flat `pyproject.toml` pulled every plugin's deps for every
user. User explicitly asked for scale:
- Each plugin = its own `pyproject.toml`
- Top-level meta-package declares optional extras
- `pip install squid-tools[stitching,decon]`

Design captured in
`references/specs/2026-04-21-v1-dependency-management.md`.

### "Customer interview where they click post-processing modules"

The user imagined a download page where a researcher checks the
boxes for what they need and gets a .exe/.AppImage with exactly
those modules. Key points:
- Size estimate visible per module
- GPU extra hidden on macOS (no CuPy wheels)
- CI rebuilds bundles on every commit, uploads to R2
- Download page is Cloudflare Pages; pip index is R2
- The installer app is a small PySide6 wizard that shells to pip
  with the selected extras

Implementation is v2 A1/A2; design is v1.

---

## 6. Metadata awareness

### "Make the whole suite metadata aware"

Three Squid output formats (OME-TIFF, Individual, Zarr) must
produce the same data model. Plugins consume metadata from the
model (pixel size, NA, wavelength, z-step), never hardcoded.

**Legacy support commitment.** The user said: support legacy
formats for the next year or so. Implications:
- Format detection is sticky (`core/readers/__init__.py::
  detect_reader`).
- New Squid formats add a reader class; old ones stay.
- v2 ships an auto-reader generator for new formats.

### "Hardcoded pixel size 0.325 isn't OK"

Specifically called out. Fix: `default_params` raises if optical
metadata is missing. No more silent fallbacks.

### "Absorb the OME sidecar convention"

Each plugin run should record in `.squid-tools/manifest.json`
(ProcessingRun entries). Original files never modified. This is
now wired in `_on_run_complete` and `_on_run_failed`.

### "Three-node network"

From v1 spec (carried forward to v2 F3):
1. Dev machine (Mac) runs absorber
2. Cloud R2 + build server hosts test data, publishes wheels
3. Web demo (Cloudflare Pages) lets customers try squid-tools
   without installing

---

## 7. Process / working style

### "No shortcuts because of friction"

When the user pushes back, the right response is to fix things
properly — not smaller. If a fix has multiple parts, do them all.

### "Small batches → one concern → one fix → one verify"

Ground rule for feedback iterations. One punch per commit.

### "Let me know when I should actually test functionally"

The user doesn't want a bunch of cycles merged in one go and then
have to test everything at once. They want milestone-size commits
they can test in single-feature chunks.

### "Ground my prompts to code that already exists"

When the user gives a prompt, my first job is to find the
file:line it corresponds to and only THEN propose a change.

### "Simplify and clean"

Recurrent late-session theme. The user was frustrated with the
volume of code I'd added. Simpler diffs, clearer naming, less
scaffolding.

---

## 8. Specific user-stated asks that drove decisions

From my session memory, organized by where they landed:

### GUI layout
- Viewer canvas must be centered (→ `SquareContainer`)
- Viewer canvas must be square (→ `SquareContainer`)
- Processing tabs not on top (eats height) → moved to left col
- Left column too wide (260 → 190) → collapsible splitter
- Two columns of sliders confusing → single slider per channel
- Borders off by default → `_borders_visible = False`
- Copy: "Apply to viewer" not "Enable in pipeline"
- Tab titles are umbrella categories, algorithm name in the toggle

### Stitcher
- Unify the two registration paths (engine vs plugin) → pick plugin
- Fusion missing from reference → add `fuse_region_to_array` +
  right-click export
- Defaults don't match reference → port from tilefusion TileFusion
  __init__
- No hardcoded pixel size → raise in `default_params` if missing

### Contrast / compositor
- Auto-contrast fails when data exceeds 2×p99 → use real sampled max
- Pan to bright region doesn't adapt → viewport-follow timer
  (500 ms debounce) on untouched channels
- Pre-compositing keeps the CPU compositor (user said "don't drop
  it, important for petabyte-scale")

### Absorption loop
- Step 4.5 added to the skill (capture GUI manifest)
- `gui_manifest.yaml` ships next to every `plugin.py`
- ProcessingTabs consumes the manifest automatically (hidden
  defaults, per-param tooltip, range constraints)

### Infrastructure
- Async tile loading (Cycle C) — worker thread + replace-semantics
- Multi-scale pyramid (Cycle D) — 5 levels, bit_length heuristic
- GPU compositing (Cycle F) — CuPy fallback to numpy
- 3D volume rendering (Cycle E) — data + canvas, no widget
  integration in v1 (deferred Cycle O, then landed)
- R2 hosting (Cycle G) — client + upload CLI
- Browser viewer (Cycle P) — static Canvas2D + tiles.json

### Logging
- Python stdlib `logging` + rotating file + Qt handler (Cycle B)
- Level filter dropdown in LogPanel
- Per-module loggers in controller, runner, engine, plugins

### Sidecar
- `.squid-tools/manifest.json` writes a ProcessingRun per run
- Params snapshot via Pydantic `.model_dump()`
- Includes tiles_processed + status

---

## 9. Things the user PROPOSED that we didn't implement

Honest flag: ideas the user raised that didn't land in v1. Mostly
scoped to v2.

- **Cell segmentation + magical brush** — v2 B1.
- **Cell tracking (transfer learning)** — v2 B2.
- **Object detection** — v2 B3.
- **Smart Acquisition CRUK 3D** — v2 B4. Acquisition-time
  feedback loop; major undertaking.
- **Media Cybernetics metadata interop** — v2 B5.
- **MCP API server** — v2 E1.
- **Navigator pane** — v2 D1.
- **Collaborative viewing** — v2 H3.
- **WebGL VolumeVisual port** — v2 H2.
- **Full NIS Elements-style ribbon** — our tabs are simpler.
- **True range slider** — would need `superqt` dep, user rejected.
- **Napari-layer-mode composite** — kept CPU compositor instead
  for petabyte scale; v2 dual-mode is the right answer.
- **Disk-backed pyramid** — v2 C3.
- **R-tree spatial index** — v2 C3.
- **Auto-reader generator** — v2 C1.
- **Formal OME schema validation** — v2 C2.
- **Live acquisition streaming** — v2 H1.

---

## 10. Open questions the user left on the table

These came up but weren't fully resolved; the next AI should
check in on them:

- **Which commercial GUI is the primary reference?** User cited
  three (NIS, Araceli, Revvity). They each have different
  metaphors. When GUI decisions conflict, which wins?
- **Should algorithm tabs be categorical umbrellas or flat?** We
  went with umbrellas (one tab per category), with a dropdown
  inside when a category has >1 plugin. The current case only
  exercises the 1-plugin-per-category path; v2 needs to validate
  the UX when e.g. denoising has aCNS + BM3D + NLM.
- **Does the user want napari as a dependency or not?** It's
  mentioned as a reference but we don't depend on it. Some
  scenarios (segmentation overlays, annotation tools) would be
  much cheaper inside napari.
- **What's the definition of "converged v1"?** The user tagged
  v1.0.0 but we're still iterating. The functional test pass
  implicitly defines it.
