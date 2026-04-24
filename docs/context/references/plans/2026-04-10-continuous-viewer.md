# Continuous Zoom Stage Viewer Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the FOV/Mosaic toggle viewer with a single continuous-zoom stage view that loads tiles on demand based on viewport, downsamples to screen resolution, and caches in an LRU. No pyramids. No pre-computation. No data duplication.

**Architecture:** A `SpatialIndex` maps (x_mm, y_mm, w_mm, h_mm) per tile from coordinates.csv. The `ViewportEngine` takes viewport bounds + screen size, queries the spatial index for visible tiles, loads them via the reader, downsamples to screen resolution, caches in LRU, and feeds textures to the vispy canvas. Pan/zoom changes the viewport, which triggers a new query. The viewer stays ahead of the user's eyes.

**Tech Stack:** vispy (SceneCanvas, PanZoomCamera), scipy.ndimage.zoom (nearest-neighbor downsampling), tifffile, existing core/ readers and cache

---

## What Gets Removed

- `squid_tools/gui/mosaic.py` (separate mosaic widget, replaced by continuous viewer)
- `squid_tools/gui/viewer.py` (separate FOV widget, replaced by continuous viewer)
- FOV/Mosaic toggle button from controls panel
- `display_mosaic()` and `display_fov()` as separate methods
- Thumbnail generation code (replaced by on-demand downsampling)

## What Gets Created

```
squid_tools/viewer/
├── spatial_index.py       # Tile spatial index from coordinates.csv
├── viewport_engine.py     # Viewport-aware tile loading + downsampling + caching
├── canvas.py              # REWRITTEN: continuous mm-space rendering
├── widget.py              # REWRITTEN: one viewer, continuous zoom, sliders
├── colormaps.py           # Unchanged
squid_tools/gui/
├── app.py                 # MODIFIED: no mode switching, one viewer
├── controls.py            # MODIFIED: remove FOV/Mosaic toggle
```

---

### Task 1: Spatial Index

**Files:**
- Create: `squid_tools/viewer/spatial_index.py`
- Create: `tests/unit/test_spatial_index.py`

The spatial index answers: "which tiles are visible in this viewport?"

- [ ] **Step 1: Write failing test**

`tests/unit/test_spatial_index.py`:
```python
"""Tests for tile spatial index."""

from squid_tools.core.data_model import FOVPosition, Region
from squid_tools.viewer.spatial_index import SpatialIndex


def _make_grid_region(nx: int, ny: int, step_mm: float, tile_w_mm: float) -> Region:
    fovs = []
    idx = 0
    for iy in range(ny):
        for ix in range(nx):
            fovs.append(FOVPosition(
                fov_index=idx,
                x_mm=ix * step_mm,
                y_mm=iy * step_mm,
            ))
            idx += 1
    return Region(region_id="test", center_mm=(0, 0, 0), fovs=fovs)


class TestSpatialIndex:
    def test_build_from_region(self) -> None:
        region = _make_grid_region(3, 3, step_mm=1.0, tile_w_mm=1.2)
        idx = SpatialIndex(region, tile_width_mm=1.2, tile_height_mm=1.2)
        assert idx.total_tiles == 9

    def test_query_full_viewport(self) -> None:
        region = _make_grid_region(3, 3, step_mm=1.0, tile_w_mm=1.2)
        idx = SpatialIndex(region, tile_width_mm=1.2, tile_height_mm=1.2)
        visible = idx.query(x_min=-1, y_min=-1, x_max=10, y_max=10)
        assert len(visible) == 9

    def test_query_partial_viewport(self) -> None:
        region = _make_grid_region(3, 3, step_mm=1.0, tile_w_mm=1.2)
        idx = SpatialIndex(region, tile_width_mm=1.2, tile_height_mm=1.2)
        # Viewport covering only top-left tile
        visible = idx.query(x_min=-0.1, y_min=-0.1, x_max=0.5, y_max=0.5)
        assert len(visible) == 1
        assert visible[0].fov_index == 0

    def test_query_empty_viewport(self) -> None:
        region = _make_grid_region(3, 3, step_mm=1.0, tile_w_mm=1.2)
        idx = SpatialIndex(region, tile_width_mm=1.2, tile_height_mm=1.2)
        visible = idx.query(x_min=100, y_min=100, x_max=200, y_max=200)
        assert len(visible) == 0

    def test_bounding_box(self) -> None:
        region = _make_grid_region(3, 3, step_mm=1.0, tile_w_mm=1.2)
        idx = SpatialIndex(region, tile_width_mm=1.2, tile_height_mm=1.2)
        bb = idx.bounding_box()
        assert bb[0] == 0.0  # x_min
        assert bb[1] == 0.0  # y_min
        assert bb[2] > 2.0   # x_max (2.0 + 1.2)
        assert bb[3] > 2.0   # y_max

    def test_query_returns_fov_positions(self) -> None:
        region = _make_grid_region(2, 2, step_mm=1.0, tile_w_mm=1.2)
        idx = SpatialIndex(region, tile_width_mm=1.2, tile_height_mm=1.2)
        visible = idx.query(x_min=0.5, y_min=0.5, x_max=2.0, y_max=2.0)
        # Should include tiles 0,1,2,3 since they all overlap this viewport
        fov_indices = {f.fov_index for f in visible}
        assert len(fov_indices) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_spatial_index.py -v`

- [ ] **Step 3: Implement SpatialIndex**

`squid_tools/viewer/spatial_index.py`:
```python
"""Spatial index for tile positions.

Maps FOV positions from coordinates.csv into a queryable index.
Query: given viewport bounds (mm), return which tiles are visible.
No pre-computation. Just geometry.
"""

from __future__ import annotations

from squid_tools.core.data_model import FOVPosition, Region


class SpatialIndex:
    """Answers: which tiles are visible in this viewport?"""

    def __init__(
        self, region: Region, tile_width_mm: float, tile_height_mm: float,
    ) -> None:
        self._fovs = region.fovs
        self._tw = tile_width_mm
        self._th = tile_height_mm

    @property
    def total_tiles(self) -> int:
        return len(self._fovs)

    def query(
        self, x_min: float, y_min: float, x_max: float, y_max: float,
    ) -> list[FOVPosition]:
        """Return FOVs whose tile footprint intersects the viewport (mm)."""
        visible: list[FOVPosition] = []
        for fov in self._fovs:
            fx_min = fov.x_mm
            fy_min = fov.y_mm
            fx_max = fov.x_mm + self._tw
            fy_max = fov.y_mm + self._th
            if fx_max > x_min and fx_min < x_max and fy_max > y_min and fy_min < y_max:
                visible.append(fov)
        return visible

    def bounding_box(self) -> tuple[float, float, float, float]:
        """Return (x_min, y_min, x_max, y_max) of all tiles in mm."""
        if not self._fovs:
            return (0, 0, 0, 0)
        xs = [f.x_mm for f in self._fovs]
        ys = [f.y_mm for f in self._fovs]
        return (min(xs), min(ys), max(xs) + self._tw, max(ys) + self._th)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_spatial_index.py -v`

- [ ] **Step 5: Commit**

```bash
git add squid_tools/viewer/spatial_index.py tests/unit/test_spatial_index.py
git commit -m "feat: tile spatial index for viewport queries"
```

---

### Task 2: Viewport Engine

**Files:**
- Create: `squid_tools/viewer/viewport_engine.py`
- Create: `tests/unit/test_viewport_engine.py`

The engine: given viewport + screen size, load visible tiles, downsample to screen resolution, cache.

- [ ] **Step 1: Write failing test**

`tests/unit/test_viewport_engine.py`:
```python
"""Tests for viewport-aware tile loading engine."""

from pathlib import Path

import numpy as np

from squid_tools.viewer.viewport_engine import ViewportEngine
from tests.fixtures.generate_fixtures import create_individual_acquisition


class TestViewportEngine:
    def test_instantiate(self) -> None:
        engine = ViewportEngine()
        assert engine is not None

    def test_load_acquisition(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=3, ny=3, nz=1, nc=1, nt=1
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        assert engine.is_loaded()

    def test_get_visible_tiles(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=3, ny=3, nz=1, nc=1, nt=1
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        bb = engine.bounding_box()
        # Request all tiles
        tiles = engine.get_tiles(
            viewport=bb, screen_width=800, screen_height=600,
            channel=0, z=0, timepoint=0,
        )
        assert len(tiles) > 0

    def test_tiles_are_downsampled(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        bb = engine.bounding_box()
        # Request at very small screen size -> heavy downsampling
        tiles = engine.get_tiles(
            viewport=bb, screen_width=100, screen_height=100,
            channel=0, z=0, timepoint=0,
        )
        for tile in tiles:
            # Each tile's data should be smaller than full res (128x128)
            assert tile.data.shape[0] <= 128
            assert tile.data.shape[1] <= 128

    def test_partial_viewport(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=3, ny=3, nz=1, nc=1, nt=1
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        bb = engine.bounding_box()
        # Viewport covering only top-left quarter
        half_x = (bb[0] + bb[2]) / 2
        half_y = (bb[1] + bb[3]) / 2
        tiles = engine.get_tiles(
            viewport=(bb[0], bb[1], half_x, half_y),
            screen_width=400, screen_height=400,
            channel=0, z=0, timepoint=0,
        )
        assert len(tiles) < 9  # fewer than all tiles

    def test_caches_tiles(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        bb = engine.bounding_box()
        t1 = engine.get_tiles(viewport=bb, screen_width=400, screen_height=400, channel=0)
        t2 = engine.get_tiles(viewport=bb, screen_width=400, screen_height=400, channel=0)
        # Same data objects from cache
        assert t1[0].data is t2[0].data

    def test_tile_has_position_and_size(self, tmp_path: Path) -> None:
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        engine = ViewportEngine()
        engine.load(acq_path, region="0")
        bb = engine.bounding_box()
        tiles = engine.get_tiles(viewport=bb, screen_width=400, screen_height=400, channel=0)
        for tile in tiles:
            assert hasattr(tile, "x_mm")
            assert hasattr(tile, "y_mm")
            assert hasattr(tile, "width_mm")
            assert hasattr(tile, "height_mm")
            assert hasattr(tile, "data")
            assert tile.width_mm > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_viewport_engine.py -v`

- [ ] **Step 3: Implement ViewportEngine**

`squid_tools/viewer/viewport_engine.py`:
```python
"""Viewport-aware tile loading engine.

Given viewport bounds + screen size:
1. Query spatial index for visible tiles
2. Compute target resolution (downsample to screen pixels)
3. Load tile from reader (or cache)
4. Downsample to target resolution
5. Return positioned tile data ready for rendering

No pyramids. No pre-computation. Faster than the user's eyes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import zoom as ndi_zoom

from squid_tools.core.cache import MemoryBoundedLRUCache
from squid_tools.core.data_model import Acquisition, FrameKey
from squid_tools.core.readers import detect_reader
from squid_tools.core.readers.base import FormatReader
from squid_tools.viewer.spatial_index import SpatialIndex


@dataclass
class VisibleTile:
    """A tile ready for rendering."""

    fov_index: int
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    data: np.ndarray  # downsampled to screen resolution


class ViewportEngine:
    """Loads visible tiles on demand, downsampled to screen resolution."""

    def __init__(self, cache_bytes: int = 256 * 1024 * 1024) -> None:
        self._acquisition: Acquisition | None = None
        self._reader: FormatReader | None = None
        self._index: SpatialIndex | None = None
        self._tile_w_mm: float = 0.0
        self._tile_h_mm: float = 0.0
        self._tile_w_px: int = 0
        self._tile_h_px: int = 0
        self._region: str = ""
        self._raw_cache = MemoryBoundedLRUCache(max_bytes=cache_bytes)
        self._display_cache: dict[str, np.ndarray] = {}
        self._last_screen_key: str = ""
        self._pipeline: list = []
        self._contrast: tuple[float, float] | None = None

    def load(self, path: Path, region: str) -> None:
        """Load acquisition and build spatial index for a region."""
        self._reader = detect_reader(path)
        self._acquisition = self._reader.read_metadata(path)
        self._region = region

        # Get tile dimensions from first FOV
        region_obj = self._acquisition.regions[region]
        first_fov = region_obj.fovs[0]
        key = FrameKey(region=region, fov=first_fov.fov_index, z=0, channel=0, timepoint=0)
        first_frame = self._reader.read_frame(key)
        self._tile_h_px, self._tile_w_px = first_frame.shape[:2]
        self._raw_cache.put(f"raw_{region}_{first_fov.fov_index}_0_0_0", first_frame)

        pixel_size = self._acquisition.objective.pixel_size_um
        self._tile_w_mm = self._tile_w_px * pixel_size / 1000
        self._tile_h_mm = self._tile_h_px * pixel_size / 1000

        self._index = SpatialIndex(region_obj, self._tile_w_mm, self._tile_h_mm)

    def is_loaded(self) -> bool:
        return self._index is not None

    def bounding_box(self) -> tuple[float, float, float, float]:
        """Stage bounding box in mm."""
        if self._index is None:
            return (0, 0, 0, 0)
        return self._index.bounding_box()

    @property
    def tile_size_mm(self) -> tuple[float, float]:
        return (self._tile_w_mm, self._tile_h_mm)

    @property
    def pixel_size_um(self) -> float:
        if self._acquisition is None:
            return 1.0
        return self._acquisition.objective.pixel_size_um

    def set_pipeline(self, transforms: list) -> None:
        """Set processing pipeline (toggle-based)."""
        self._pipeline = transforms
        self._display_cache.clear()

    def set_contrast(self, p1: float, p99: float) -> None:
        """Set global contrast range."""
        self._contrast = (p1, p99)

    def compute_contrast(
        self, channel: int = 0, z: int = 0, timepoint: int = 0, sample_every: int = 5,
    ) -> tuple[float, float]:
        """Sample tiles to compute global p1/p99 contrast."""
        if self._acquisition is None or self._reader is None:
            return (0.0, 65535.0)
        fovs = self._acquisition.regions[self._region].fovs
        pixels: list[np.ndarray] = []
        for i, fov in enumerate(fovs):
            if i % sample_every != 0:
                continue
            frame = self._load_raw(fov.fov_index, z, channel, timepoint)
            flat = frame.ravel()
            rng = np.random.default_rng(42)
            idx = rng.choice(len(flat), min(1000, len(flat)), replace=False)
            pixels.append(flat[idx])
        all_px = np.concatenate(pixels)
        p1, p99 = float(np.percentile(all_px, 1)), float(np.percentile(all_px, 99))
        if p1 == p99:
            p99 = p1 + 1
        self._contrast = (p1, p99)
        return (p1, p99)

    def get_tiles(
        self,
        viewport: tuple[float, float, float, float],
        screen_width: int,
        screen_height: int,
        channel: int = 0,
        z: int = 0,
        timepoint: int = 0,
    ) -> list[VisibleTile]:
        """Get tiles visible in viewport, downsampled to screen resolution."""
        if self._index is None or self._reader is None:
            return []

        x_min, y_min, x_max, y_max = viewport
        visible_fovs = self._index.query(x_min, y_min, x_max, y_max)

        # How many screen pixels per tile?
        vp_width_mm = max(x_max - x_min, 1e-6)
        mm_per_screen_px = vp_width_mm / max(screen_width, 1)
        target_tile_px = max(4, int(self._tile_w_mm / mm_per_screen_px))
        # Clamp to full resolution
        target_tile_px = min(target_tile_px, self._tile_w_px)

        screen_key = f"{target_tile_px}_{channel}_{z}_{timepoint}"
        cache_invalidated = screen_key != self._last_screen_key
        self._last_screen_key = screen_key

        tiles: list[VisibleTile] = []
        for fov in visible_fovs:
            display_key = f"disp_{fov.fov_index}_{screen_key}"

            if not cache_invalidated and display_key in self._display_cache:
                data = self._display_cache[display_key]
            else:
                raw = self._load_raw(fov.fov_index, z, channel, timepoint)
                # Apply pipeline
                processed = raw.astype(np.float32)
                for transform in self._pipeline:
                    processed = transform(processed)
                # Downsample to screen resolution
                if target_tile_px < self._tile_w_px:
                    factor = target_tile_px / self._tile_w_px
                    data = ndi_zoom(processed, factor, order=0)
                else:
                    data = processed
                self._display_cache[display_key] = data

            tiles.append(VisibleTile(
                fov_index=fov.fov_index,
                x_mm=fov.x_mm, y_mm=fov.y_mm,
                width_mm=self._tile_w_mm, height_mm=self._tile_h_mm,
                data=data,
            ))

        return tiles

    def _load_raw(self, fov: int, z: int, channel: int, timepoint: int) -> np.ndarray:
        """Load raw frame with caching."""
        cache_key = f"raw_{self._region}_{fov}_{z}_{channel}_{timepoint}"
        cached = self._raw_cache.get(cache_key)
        if cached is not None:
            return cached
        if self._reader is None:
            raise RuntimeError("No reader")
        key = FrameKey(region=self._region, fov=fov, z=z, channel=channel, timepoint=timepoint)
        frame = self._reader.read_frame(key)
        self._raw_cache.put(cache_key, frame)
        return frame
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_viewport_engine.py -v`

- [ ] **Step 5: Commit**

```bash
git add squid_tools/viewer/viewport_engine.py tests/unit/test_viewport_engine.py
git commit -m "feat: viewport engine with on-demand loading, downsampling, caching"
```

---

### Task 3: Rewrite Canvas and Widget (Continuous Zoom)

**Files:**
- Rewrite: `squid_tools/viewer/canvas.py`
- Rewrite: `squid_tools/viewer/widget.py`
- Remove: `squid_tools/gui/mosaic.py`
- Remove: `squid_tools/gui/viewer.py`
- Modify: `squid_tools/gui/controls.py` (remove FOV/Mosaic toggle)

- [ ] **Step 1: Rewrite canvas.py**

The canvas is simplified. It receives a list of `VisibleTile` objects and renders them. That's it.

`squid_tools/viewer/canvas.py`:
```python
"""Vispy stage canvas in mm coordinates.

Receives VisibleTile objects from the viewport engine and renders them.
Pan/zoom operates in mm. Borders drawn on top.
"""

from __future__ import annotations

import numpy as np
import vispy.app
from vispy.scene import SceneCanvas
from vispy.scene.cameras import PanZoomCamera
from vispy.scene.visuals import Image, Line
from vispy.visuals.transforms import STTransform

from squid_tools.viewer.viewport_engine import VisibleTile

vispy.app.use_app("pyside6")


def _to_float32(data: np.ndarray) -> np.ndarray:
    if data.dtype == np.float32:
        return data
    return data.astype(np.float32)


class StageCanvas:
    """Renders tiles in mm stage coordinates."""

    def __init__(self) -> None:
        self._canvas = SceneCanvas(keys="interactive", show=False)
        self._view = self._canvas.central_widget.add_view()
        self._view.camera = PanZoomCamera(aspect=1)

        self._tiles: dict[int, Image] = {}      # fov_index -> Image
        self._borders: dict[int, Line] = {}      # fov_index -> Line
        self._borders_visible = True
        self._clim: tuple[float, float] | None = None
        self._cmap: str = "grays"

    def set_clim(self, clim: tuple[float, float]) -> None:
        self._clim = clim
        for img in self._tiles.values():
            img.clim = clim

    def set_cmap(self, cmap: str) -> None:
        self._cmap = cmap

    def render_tiles(self, tiles: list[VisibleTile]) -> None:
        """Update the display with a new set of visible tiles."""
        # Remove tiles no longer visible
        visible_ids = {t.fov_index for t in tiles}
        for fov_id in list(self._tiles.keys()):
            if fov_id not in visible_ids:
                self._tiles[fov_id].parent = None
                del self._tiles[fov_id]
        for fov_id in list(self._borders.keys()):
            if fov_id not in visible_ids:
                self._borders[fov_id].parent = None
                del self._borders[fov_id]

        # Add or update visible tiles
        for tile in tiles:
            data = _to_float32(tile.data)
            h_px, w_px = data.shape[:2]
            sx = tile.width_mm / w_px if w_px > 0 else 1.0
            sy = tile.height_mm / h_px if h_px > 0 else 1.0
            clim = self._clim or (float(data.min()), float(data.max()))
            transform = STTransform(
                scale=(sx, sy, 1), translate=(tile.x_mm, tile.y_mm, 0),
            )

            if tile.fov_index in self._tiles:
                self._tiles[tile.fov_index].set_data(data)
                self._tiles[tile.fov_index].transform = transform
                self._tiles[tile.fov_index].clim = clim
            else:
                img = Image(
                    data, cmap=self._cmap, clim=clim,
                    parent=self._view.scene,
                )
                img.transform = transform
                self._tiles[tile.fov_index] = img

            # Border
            self._ensure_border(tile)

    def _ensure_border(self, tile: VisibleTile) -> None:
        corners = np.array([
            [tile.x_mm, tile.y_mm],
            [tile.x_mm + tile.width_mm, tile.y_mm],
            [tile.x_mm + tile.width_mm, tile.y_mm + tile.height_mm],
            [tile.x_mm, tile.y_mm + tile.height_mm],
            [tile.x_mm, tile.y_mm],
        ], dtype=np.float32)

        if tile.fov_index in self._borders:
            self._borders[tile.fov_index].set_data(pos=corners)
        else:
            line = Line(
                pos=corners, color="yellow", width=2,
                connect="strip", parent=self._view.scene,
            )
            line.order = -1
            self._borders[tile.fov_index] = line

        self._borders[tile.fov_index].visible = self._borders_visible

    def set_borders_visible(self, visible: bool) -> None:
        self._borders_visible = visible
        for b in self._borders.values():
            b.visible = visible

    def clear(self) -> None:
        for img in self._tiles.values():
            img.parent = None
        self._tiles.clear()
        for b in self._borders.values():
            b.parent = None
        self._borders.clear()

    def set_range(self, x_min: float, y_min: float, x_max: float, y_max: float) -> None:
        self._view.camera.set_range(x=(x_min, x_max), y=(y_min, y_max))

    def get_viewport(self) -> tuple[float, float, float, float]:
        rect = self._view.camera.rect
        return (rect.left, rect.bottom, rect.right, rect.top)

    def get_screen_size(self) -> tuple[int, int]:
        return (self._canvas.size[0], self._canvas.size[1])

    def native_widget(self) -> object:
        return self._canvas.native

    def connect_draw(self, callback: object) -> None:
        """Connect to canvas draw event (fires after pan/zoom)."""
        self._canvas.events.draw.connect(callback)
```

- [ ] **Step 2: Rewrite widget.py**

`squid_tools/viewer/widget.py`:
```python
"""Continuous zoom stage viewer.

One viewer. No mode switching. Zoom controls resolution.
Pan loads new tiles on demand. Sliders work at every zoom level.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from squid_tools.viewer.canvas import StageCanvas
from squid_tools.viewer.colormaps import get_channel_colormap
from squid_tools.viewer.viewport_engine import ViewportEngine


class ViewerWidget(QWidget):
    """Continuous zoom stage viewer."""

    fov_clicked = Signal(str, int)  # region_id, fov_index

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._canvas = StageCanvas()
        self._engine = ViewportEngine()
        self._region: str = ""
        self._channels: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        native = self._canvas.native_widget()
        if native is not None:
            layout.addWidget(native, stretch=1)  # type: ignore[arg-type]

        # Sliders
        slider_row = QHBoxLayout()
        slider_row.setContentsMargins(4, 2, 4, 2)

        slider_row.addWidget(QLabel("Ch"))
        self.channel_slider = QSlider(Qt.Orientation.Horizontal)
        self.channel_slider.setRange(0, 0)
        self.channel_slider.setToolTip("Channel")
        self.channel_slider.valueChanged.connect(self._on_slider_changed)
        slider_row.addWidget(self.channel_slider)

        slider_row.addWidget(QLabel("Z"))
        self.z_slider = QSlider(Qt.Orientation.Horizontal)
        self.z_slider.setRange(0, 0)
        self.z_slider.setToolTip("Z-level")
        self.z_slider.valueChanged.connect(self._on_slider_changed)
        slider_row.addWidget(self.z_slider)

        slider_row.addWidget(QLabel("T"))
        self.t_slider = QSlider(Qt.Orientation.Horizontal)
        self.t_slider.setRange(0, 0)
        self.t_slider.setToolTip("Timepoint")
        self.t_slider.valueChanged.connect(self._on_slider_changed)
        slider_row.addWidget(self.t_slider)

        layout.addLayout(slider_row)

        # Debounce timer for viewport changes (pan/zoom)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(50)  # 50ms debounce
        self._refresh_timer.timeout.connect(self._refresh)

        # Connect to canvas draw event for viewport-driven loading
        self._canvas.connect_draw(self._on_draw)

    def load_acquisition(self, path: Path, region: str) -> None:
        """Load acquisition and display the stage view."""
        from squid_tools.core.readers import detect_reader

        reader = detect_reader(path)
        acq = reader.read_metadata(path)

        self._engine.load(path, region)
        self._region = region
        self._channels = [ch.name for ch in acq.channels]

        # Configure sliders
        self.channel_slider.setRange(0, max(0, len(acq.channels) - 1))
        nz = acq.z_stack.nz if acq.z_stack else 1
        self.z_slider.setRange(0, max(0, nz - 1))
        nt = acq.time_series.nt if acq.time_series else 1
        self.t_slider.setRange(0, max(0, nt - 1))

        # Set colormap from first channel
        if self._channels:
            cmap = get_channel_colormap(self._channels[0])
            self._canvas.set_cmap(cmap)

        # Compute contrast
        ch = self.channel_slider.value()
        p1, p99 = self._engine.compute_contrast(channel=ch)
        self._canvas.set_clim((p1, p99))

        # Fit to bounding box
        bb = self._engine.bounding_box()
        self._canvas.set_range(*bb)

        # Initial render
        self._refresh()

    def set_pipeline(self, transforms: list) -> None:
        self._engine.set_pipeline(transforms)
        self._refresh()

    def set_borders_visible(self, visible: bool) -> None:
        self._canvas.set_borders_visible(visible)

    def _on_draw(self, event: object) -> None:
        """Canvas was drawn (after pan/zoom). Schedule a refresh."""
        self._refresh_timer.start()

    def _on_slider_changed(self) -> None:
        """Slider changed. Update colormap and refresh."""
        ch = self.channel_slider.value()
        if ch < len(self._channels):
            cmap = get_channel_colormap(self._channels[ch])
            self._canvas.set_cmap(cmap)
        # Recompute contrast for new channel
        p1, p99 = self._engine.compute_contrast(
            channel=ch, z=self.z_slider.value(), timepoint=self.t_slider.value(),
        )
        self._canvas.set_clim((p1, p99))
        self._engine._display_cache.clear()
        self._refresh()

    def _refresh(self) -> None:
        """Load and render tiles for the current viewport."""
        if not self._engine.is_loaded():
            return
        viewport = self._canvas.get_viewport()
        sw, sh = self._canvas.get_screen_size()
        if sw == 0 or sh == 0:
            return

        tiles = self._engine.get_tiles(
            viewport=viewport,
            screen_width=sw, screen_height=sh,
            channel=self.channel_slider.value(),
            z=self.z_slider.value(),
            timepoint=self.t_slider.value(),
        )
        self._canvas.render_tiles(tiles)

    def contextMenuEvent(self, event: object) -> None:  # type: ignore[override]  # noqa: N802
        menu = QMenu(self)
        fit_action = QAction("Fit View", self)
        fit_action.triggered.connect(lambda: (
            self._canvas.set_range(*self._engine.bounding_box()),
            self._refresh(),
        ))
        menu.addAction(fit_action)
        toggle_borders = QAction("Toggle Borders", self)
        toggle_borders.triggered.connect(
            lambda: self._canvas.set_borders_visible(not self._canvas._borders_visible)
        )
        menu.addAction(toggle_borders)
        menu.exec(event.globalPos())  # type: ignore[union-attr]
```

- [ ] **Step 3: Remove old viewer/mosaic adapters and update controls**

Delete `squid_tools/gui/viewer.py` and `squid_tools/gui/mosaic.py`.

Rewrite `squid_tools/gui/controls.py` to remove the FOV/Mosaic toggle:

```python
"""Left controls panel: border overlay, layer controls."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget


class ControlsPanel(QWidget):
    """Left panel with border overlay and layer controls."""

    borders_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        layout.addWidget(QLabel("Overlay"))
        self.borders_checkbox = QCheckBox("Show FOV Borders")
        self.borders_checkbox.setToolTip("Show/hide FOV border rectangles")
        self.borders_checkbox.setChecked(True)
        self.borders_checkbox.toggled.connect(self.borders_toggled.emit)
        layout.addWidget(self.borders_checkbox)

        layout.addStretch()
```

- [ ] **Step 4: Rewrite app.py for continuous viewer**

The MainWindow no longer has FOV/mosaic modes. It has one `ViewerWidget`. Opening an acquisition loads the stage view. Processing toggles modify the pipeline. Everything else stays.

Key changes to `squid_tools/gui/app.py`:
- Remove `_viewer_stack`, `_fov_viewer`, `_mosaic_viewer`
- Add `self._viewer = None` (lazily created ViewerWidget)
- `open_acquisition` creates the viewer and calls `viewer.load_acquisition(path, first_region)`
- `_on_region_selected` calls `viewer.load_acquisition(path, region_id)` (reloads for new region)
- `_on_toggle_changed` rebuilds pipeline and calls `viewer.set_pipeline(transforms)`
- `_on_borders_toggled` calls `viewer.set_borders_visible(visible)`
- Remove `_on_view_mode_changed`, `_show_fov`, `_show_mosaic`
- Remove imports of `SingleFOVViewer`, `MosaicView`

- [ ] **Step 5: Update tests**

Update `tests/integration/test_gui_smoke.py`:
- Remove tests for `view_toggle_button`, `current_view_mode`
- Update `test_main_window_has_panels` to not check for mosaic/FOV modes

Update `tests/unit/test_gui_controls.py`:
- Remove tests for `view_toggle_button`, `view_mode_changed`, `current_view_mode`
- Keep border checkbox tests

Remove outdated tests from `tests/unit/test_viewer_widget.py` that reference `display_fov`, `display_mosaic`, `set_mode`, `current_mode`.

- [ ] **Step 6: Run full test suite**

Run: `QT_QPA_PLATFORM=offscreen pytest -v --tb=short`

- [ ] **Step 7: Run ruff**

Run: `ruff check squid_tools/ tests/`

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: continuous zoom stage viewer (no mode switching, on-demand tile loading)"
```

---

### Task 4: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `QT_QPA_PLATFORM=offscreen pytest -v --tb=short`

- [ ] **Step 2: Run ruff**

Run: `ruff check squid_tools/ tests/ installer/`

- [ ] **Step 3: Verify CLI**

Run: `QT_QPA_PLATFORM=offscreen python -m squid_tools --version`

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "chore: continuous viewer verification"
```
