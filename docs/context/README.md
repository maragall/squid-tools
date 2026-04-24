# Squid-Tools Context Bundle

**Purpose.** Everything a new AI assistant needs to pick up work on
squid-tools without re-reading the full conversation history. If you
are such an assistant: read this file first, then consult the
documents it points to.

**Generated.** 2026-04-21 by the session's working agent (Claude
Opus 4.7, 1M context).

---

## How to use this directory

Read in this order:

1. **`00-project-state.md`** — what squid-tools is right now, the
   architecture at a glance, what's merged, what's deferred. Start
   here.
2. **`01-collaboration-notes.md`** — how the user (Julio Maragall,
   `maragall@`) works. Non-negotiable rules. Ways I've failed and how
   to avoid repeating them.
3. **`02-brainstorming-highlights.md`** — user-originated design ideas
   captured across the session. Some verbatim; some reconstructed.
   Flag: I do NOT have the user's raw prompts on disk. This is my
   best honest reconstruction.
4. **`03-feedback-log.md`** — testing feedback the user gave during
   iterative testing, what each prompted, whether it landed in v1 or
   was deferred.
5. **`04-cycle-history.md`** — chronological walk through Cycles A-P
   plus convergence. What landed, why, what broke, what was punted.
6. **`05-bug-recurrences.md`** — bugs that bit more than once, what
   the root cause was, the pattern to watch for.
7. **`06-glossary.md`** — terms, conventions, abbreviations.
8. **`references/`** — verbatim copies of every spec, plan, audit,
   and the absorber skill file. These are the primary sources; the
   top-level docs in this directory synthesize across them.

Every document in this directory is markdown. No code, no secrets.
Total budget: ~5-8k lines. Designed to be pasted wholesale into
another AI's context window.

---

## What this bundle is NOT

- **Not a verbatim transcript.** I don't have the user's messages
  saved. What I have is commit messages, spec docs, and memory of
  the iteration. Anything I attribute to the user directly is
  reconstruction; treat it as lossy.
- **Not a code tour.** The source tree is the canonical code. Read
  `squid_tools/` and `tests/` directly; this bundle tells you WHY
  things are shaped the way they are.
- **Not a v2 plan.** See `references/specs/2026-04-21-v2-design.md`
  for the full v2 scope. `00-project-state.md` summarizes.

---

## Directory layout

```
docs/context/
├── README.md                         # (this file)
├── 00-project-state.md               # current state + architecture
├── 01-collaboration-notes.md         # how to work with this user
├── 02-brainstorming-highlights.md    # ideas the user originated
├── 03-feedback-log.md                # testing feedback + resolutions
├── 04-cycle-history.md               # cycle-by-cycle narrative
├── 05-bug-recurrences.md             # repeated bugs + root causes
├── 06-glossary.md                    # terms and conventions
└── references/                       # verbatim canonical sources
    ├── user-facing-README.md
    ├── algorithm-absorber-skill.md
    ├── specs/                        # 11 design specs
    ├── plans/                        # 15 implementation plans
    └── audits/                       # reinvention audit
```

---

## One-paragraph summary (for a fresh AI)

Squid-Tools is a PySide6 + vispy desktop viewer + post-processing
connector for Cephla-Lab/Squid microscopy. It reads three Squid
output formats (OME-TIFF, individual images, Zarr), shows a
continuous-zoom stage view with multi-scale pyramid, and runs
processing plugins (flatfield, stitching, deconvolution, phase-from-
defocus, aCNS denoising, background subtraction) on user-selected
FOVs. Plugins are discovered via entry points; each ships a
`gui_manifest.yaml` capturing the source repo's scientific wisdom
(parameter defaults, which are user-exposed). v1 is at tag `v1.0.0`
with 402 tests passing. The user tests on a real 70-FOV
4-channel 10x mouse brain dataset and iterates with concrete GUI
and correctness feedback. The project is actively under review — do
not refactor broadly; ground every change in `file:line` evidence.

## Canonical pitch (from the user, 2026-04-21)

> I've finished Squid-Tools v1. The architecture supports an
> "algorithm-absorber" agent that handles ~85% of the work to port
> any post-processing repo into our plugin layer. v1 ships a live-
> processing suite with eight post-processing modules, leverages
> Linux/Windows desktop GPUs, and uses viewport-aware lazy loading
> so petabyte-scale datasets stay responsive.

Note on the "eight post-processing modules": at the time of writing
the tree has **six** merged plugins (Flatfield, Stitcher,
Deconvolution, Phase-from-Defocus, aCNS, sep.Background). The "eight"
figure reflects the user's mental model that includes the next two
absorptions already spec'd (likely cell segmentation + background
subtraction variants, or cell tracking). The absorber is designed to
handle additional absorptions mechanically — the count will grow.

## Essence of v1 (user's framing)

"A whole pipeline of markdowns and skills." v1 is not just code —
it's the absorber protocol + the context bundle + the plugin ABC +
the gui_manifest contract + the reference repos in `_audit/`. An
agent with this bundle should be able to absorb the next algorithm
in one session.
