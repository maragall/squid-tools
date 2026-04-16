# Selection Model + Live Processing Design Spec

## Purpose

Replace the current toggle-only processing model with a selection-based workflow where users can drag-select FOVs and run processing on the selection with live visual feedback. Retrofit the two existing algorithms (flatfield, stitcher) with their custom live behaviors so subsequent algorithm absorptions follow the same pattern.

**Audience:** Life sciences researchers. The interaction must be immediately obvious: shift+drag to select, click Run to process, watch it happen live.

**Guiding principle:** The user sees what the algorithm does. Each processing step animates visibly. Nothing happens in the background without feedback in the log console.

---

## Scope

**IN:**
- Shift+drag rectangle selection on stage canvas
- `SelectionState` tracking selected FOV indices
- Selected tiles render with Cephla-blue borders (unselected stay yellow)
- Processing tabs refactor: toggle (pipeline activation) + Run button (calibrate/compute)
- Auto-run on first toggle (user doesn't click Run separately the first time)
- `AlgorithmRunner` QThread for background processing with progress signals
- Extended `ProcessingPlugin` ABC with optional `run_live()` method (default tile-by-tile)
- `FlatfieldPlugin.run_live()`: calibrate-then-apply with phase progress
- `StitcherPlugin.run_live()`: progressive pairwise registration, tiles shift live
- Log console messages for selection count, calibration progress, completion

**OUT (future cycles):**
- Cancel/pause/resume button during processing
- Click-to-select individual tiles (drag-box only this cycle)
- Ctrl+click additive selection, Shift+click range selection
- Select-all keyboard shortcut
- Selection persistence across acquisition reloads
- Custom `run_live()` for algorithms beyond flatfield and stitcher
- Progress bar widget in status bar
- Selection invert, select-region, rubber-band modifications

---

## Architecture

```
StageCanvas (vispy)
  |
  | shift+drag -> emit selection_drawn(x_min_mm, y_min_mm, x_max_mm, y_max_mm)
  v
ViewerWidget
  |
  | query SpatialIndex for FOVs in rectangle
  | update SelectionState
  v
SelectionState (QObject)
  |
  | emit selection_changed(set[int])
  v
[Canvas re-renders blue borders] <-> [ProcessingTabs update] <-> [LogPanel logs count]


User clicks Run on a tab:

ProcessingTabs -> run_requested(plugin_name, params)
                  |
                  v
             AppController -> get selection from SelectionState
                  |
                  v
             AlgorithmRunner (QThread)
                  |
                  | plugin.run_live(selection, engine, params, progress_callback)
                  |
                  +--- progress signals to GUI thread
                  +--- engine.set_position_overrides() for live tile shifts
                  +--- engine.set_pipeline() for per-tile transforms
                  v
             run_complete -> toggle auto-activates, status updates
```

---

## Components

### 1. SelectionState

**File:** `squid_tools/viewer/selection.py`

```python
from PySide6.QtCore import QObject, Signal


class SelectionState(QObject):
    """Tracks currently selected FOV indices. Thread-safe via Qt signals."""

    selection_changed = Signal(set)  # set[int] of FOV indices

    def __init__(self) -> None:
        super().__init__()
        self._selected: set[int] = set()

    @property
    def selected(self) -> set[int]:
        """Return a copy of the currently selected indices."""
        return self._selected.copy()

    def set_selection(self, indices: set[int]) -> None:
        """Replace the current selection. Emits selection_changed if different."""
        ...

    def clear(self) -> None:
        """Clear the selection."""
        ...

    def is_empty(self) -> bool:
        return len(self._selected) == 0
```

### 2. StageCanvas drag-box

**File:** `squid_tools/viewer/canvas.py` (modified)

Add:
- `selection_drawn = Signal(tuple)` — emits `(x_min_mm, y_min_mm, x_max_mm, y_max_mm)`
- Mouse event handlers:
  - `shift+press`: start rectangle at click position (in mm scene coords)
  - `shift+drag`: update rectangle endpoint; draw as a 1px Cephla-blue Line visual
  - `shift+release`: emit `selection_drawn`, remove rectangle visual
- Without shift: existing PanZoomCamera behavior (unchanged)
- `set_border_colors(selected_ids: set[int])`: re-render borders with Cephla-blue for selected, yellow for unselected

### 3. ViewerWidget

**File:** `squid_tools/viewer/widget.py` (modified)

- Add `self._selection = SelectionState()` instance
- Connect `canvas.selection_drawn` to `_on_selection_drawn()`
- `_on_selection_drawn(rect)`: query `engine._index.query(*rect)`, convert to `set[int]`, call `self._selection.set_selection(...)`
- Connect `self._selection.selection_changed` to update canvas border colors
- Expose `self.selection` as a public attribute

### 4. ProcessingTabs refactor

**File:** `squid_tools/gui/processing_tabs.py` (rewritten)

Each `_PluginTab`:
- `QCheckBox` "Active in pipeline" (replaces current toggle label)
- Parameter widgets (unchanged)
- **NEW** `QPushButton` "Calibrate / Compute" (label varies per plugin)
- **NEW** `QLabel` status line below the button: "Not calibrated" / "Calibrating..." / "Applied to N tiles" / "Failed: <reason>"

New signals:
- `toggle_changed(str, bool)` — existing
- `run_requested(str, object)` — NEW, emitted when Run button clicked. Second arg is params dict.
- `set_status(str, str)` — programmatic status update (plugin_name, status_text)

Auto-run logic: on first toggle ON, if plugin has no cached calibration state, emit `run_requested` automatically. Track per-plugin `_calibrated: dict[str, bool]`.

### 5. ProcessingPlugin ABC extension

**File:** `squid_tools/processing/base.py` (modified)

Add:

```python
from collections.abc import Callable

class ProcessingPlugin(ABC):
    # ... existing methods ...

    def run_live(
        self,
        selection: set[int] | None,
        engine: "ViewportEngine",
        params: BaseModel,
        progress: Callable[[str, int, int], None],
    ) -> None:
        """Run this plugin live with progress feedback.

        Default implementation iterates the selection (or all FOVs if None)
        and calls process() per tile, emitting progress per tile.

        Override for custom live behaviors (calibrate-then-apply, progressive
        registration, brush interaction, etc.).

        Args:
            selection: FOV indices to process. None means all FOVs.
            engine: ViewportEngine for loading tiles and updating state.
            params: Plugin-specific Pydantic parameters.
            progress: Callback (phase_name, current, total) called during work.

        Raises:
            Any exception the plugin might raise. AlgorithmRunner catches
            and reports via status.
        """
        # Default implementation
        ...
```

The default:
```python
def run_live(self, selection, engine, params, progress):
    indices = selection if selection else set(engine.all_fov_indices())
    indices_list = sorted(indices)
    total = len(indices_list)
    for i, fov in enumerate(indices_list):
        frame = engine.get_raw_frame(fov, z=0, channel=0, timepoint=0)
        result = self.process(frame, params)
        engine.cache_processed_tile(fov, result)
        progress("Processing", i + 1, total)
```

(`engine.all_fov_indices()` and `engine.cache_processed_tile()` are helpers we add.)

### 6. AlgorithmRunner

**File:** `squid_tools/gui/algorithm_runner.py` (new)

```python
from PySide6.QtCore import QObject, QThread, Signal
from pydantic import BaseModel


class AlgorithmRunner(QObject):
    """Runs a plugin's run_live() in a background QThread with progress signals."""

    progress_updated = Signal(str, str, int, int)  # (plugin_name, phase, current, total)
    run_complete = Signal(str, int)                # (plugin_name, tiles_processed)
    run_failed = Signal(str, str)                  # (plugin_name, error_message)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._worker_thread: QThread | None = None

    def run(
        self,
        plugin: ProcessingPlugin,
        selection: set[int] | None,
        engine: ViewportEngine,
        params: BaseModel,
    ) -> None:
        """Start the plugin in a background thread. Emits progress signals."""
        ...
```

The runner marshals progress to the GUI thread. Only one run can be in flight at a time (for this cycle). A second run request while one is running is queued or rejected (we pick rejected — log "Wait for current run to finish").

### 7. FlatfieldPlugin.run_live (custom)

**File:** `squid_tools/processing/flatfield/plugin.py` (modified)

```python
def run_live(self, selection, engine, params, progress):
    # Phase 1: Calibrate
    progress("Calibrating", 0, 2)
    candidates = selection if selection else set(engine.all_fov_indices())
    # Sample up to N random tiles for flatfield estimation
    sample_indices = random.sample(sorted(candidates), min(20, len(candidates)))
    tiles = []
    for i, fov in enumerate(sample_indices):
        tiles.append(engine.get_raw_frame(fov, z=0, channel=0, timepoint=0))
        progress("Calibrating", i + 1, len(sample_indices))
    flatfield = compute_flatfield(tiles)  # existing BaSiCPy / scipy code

    # Phase 2: Apply
    progress("Applying", 0, 1)
    engine.set_pipeline([lambda frame: apply_flatfield(frame, flatfield)])
    engine.invalidate_display_cache()
    progress("Applying", 1, 1)
```

### 8. StitcherPlugin.run_live (custom)

**File:** `squid_tools/processing/stitching/plugin.py` (modified)

```python
def run_live(self, selection, engine, params, progress):
    # Phase 1: Find pairs
    progress("Finding pairs", 0, 1)
    indices = selection if selection else set(engine.visible_fov_indices())
    positions = engine.get_nominal_positions(indices)
    pairs = find_adjacent_pairs(positions, ...)
    progress("Finding pairs", 1, 1)

    # Phase 2: Register progressively
    total = len(pairs)
    registered = {}
    for i, (fov_a, fov_b) in enumerate(pairs):
        shift = register_pair(engine.get_raw_frame(fov_a), engine.get_raw_frame(fov_b))
        registered[fov_b] = positions[fov_b] + shift_to_mm(shift, engine.pixel_size_um)
        # Stream the position override so the user sees the tile shift live
        engine.set_position_overrides(registered)
        progress("Registering", i + 1, total)

    # Phase 3: Global optimization
    progress("Optimizing", 0, 1)
    optimized = two_round_optimization(registered, ...)
    engine.set_position_overrides(optimized)
    progress("Optimizing", 1, 1)
```

### 9. ViewportEngine additions

**File:** `squid_tools/viewer/viewport_engine.py` (modified)

Add helpers:
- `all_fov_indices() -> set[int]`: all FOV indices in the current region
- `visible_fov_indices() -> set[int]`: FOVs in current viewport (shortcut)
- `invalidate_display_cache()`: existing, already exposed
- `get_nominal_positions(indices) -> dict[int, tuple[float, float]]`: FOV mm positions from coordinates.csv
- `cache_processed_tile(fov, data)`: optional fast path for default `run_live()`

---

## Data Flow

See Section 3 of brainstorming notes above. Summarized:

1. **Shift+drag** on canvas → rectangle emits mm bounds → SpatialIndex query → SelectionState update → canvas re-renders blue borders
2. **Run click** → AppController fetches selection → AlgorithmRunner starts plugin in QThread → progress signals update status → engine state mutations trigger canvas re-renders
3. **First toggle ON** → if not calibrated, auto-emit run_requested (as if user clicked Run)

---

## Threading

- GUI thread: all UI, SelectionState, engine reads, border re-renders
- Runner thread: calls `plugin.run_live()`, may take seconds for registration
- Progress callback marshals across threads via Qt signal (auto-handled)
- `engine._raw_cache` already has threading.Lock
- `engine._position_overrides`: add threading.Lock for writes during registration
- Only one `AlgorithmRunner.run()` in flight at a time. Second request logs "Wait for current run" and is rejected.

---

## Error Handling

| Failure | Behavior |
|---------|----------|
| No acquisition loaded | Run button disabled. Status: "Open an acquisition first." |
| Calibration fails (e.g., insufficient samples) | Status: "Failed: {reason}". Toggle stays OFF. Log full trace. |
| Registration of a pair fails | Skip that pair, continue. Status at end: "Applied to N of M pairs (M-N failures)". |
| Plugin raises unexpected exception | Runner catches, emits `run_failed`. Status: "Error: {exception}". Toggle stays OFF. |
| Run requested while another is running | Log: "Wait for current run to finish". Second request ignored. |

---

## UX Details

**Selection visuals:**
- Rectangle while dragging: 1px outline, color `#2A82DA` (Cephla-blue), no fill
- Selected tile borders: `#2A82DA` 2px (replaces yellow)
- Unselected tile borders: yellow 2px (unchanged)
- Selection count in log panel: `[HH:MM:SS] 24 tiles selected`
- Click anywhere without shift: preserves current selection (pan/zoom only)
- Shift+drag on empty canvas area: selects no tiles, effectively clears if release without dragging over any

**Processing tab states:**
- Initial: toggle unchecked, Run button enabled, status "Not calibrated"
- Running: toggle disabled during run, Run button disabled, status shows current phase
- Success: toggle auto-checks (first run only), Run button re-enabled, status "Applied to N tiles"
- Failure: toggle stays off, Run button re-enabled, status red text with reason

**First-time-use flow:**
1. User opens acquisition
2. Sees tiles with yellow borders
3. Opens Flatfield tab, clicks "Calibrate / Compute"
4. Status updates live: "Calibrating 5/20..." → "Applying..." → "Applied to 70 tiles"
5. Toggle auto-checks
6. Tiles re-render with flatfield applied

---

## Future Cycles (what this enables)

This cycle lays the foundation for:
- New algorithm absorptions override `run_live()` to define their live behavior
- The algorithm absorber skill is updated with the `run_live` requirement
- Select-all (Ctrl+A) added as a quick follow-up
- Cancel button wired to runner thread (we already have the threading model)
- Custom live behaviors for decon, phase, denoising come as their plugins get absorbed

---

## Testing Plan

**(Written at end of all cycles — functional user workflow tests for the complete integrated product. Per-cycle TDD is handled by superpowers during implementation.)**

Placeholder: this cycle's TDD tests live in its implementation plan. The spec's Testing Plan section will be written when all planned cycles are complete, describing end-to-end user workflows to validate the full product.
