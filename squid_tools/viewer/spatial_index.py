"""Spatial index for tile positions.

Maps FOV positions from coordinates.csv into a queryable index.
Query: given viewport bounds (mm), return which tiles are visible.
Grid-based dict index for O(viewport_area / cell_area) queries.
"""

from __future__ import annotations

import math
from collections import defaultdict

from squid_tools.core.data_model import FOVPosition, Region


class SpatialIndex:
    """Answers: which tiles are visible in this viewport?"""

    def __init__(
        self, region: Region, tile_width_mm: float, tile_height_mm: float,
    ) -> None:
        self._fovs = region.fovs
        self._tw = tile_width_mm
        self._th = tile_height_mm

        # Grid cell size: at least one tile fits in one cell
        self._cell_size = max(tile_width_mm, tile_height_mm)

        # Build grid index: (cell_col, cell_row) -> list of FOVPositions
        self._grid: dict[tuple[int, int], list[FOVPosition]] = defaultdict(list)
        for fov in self._fovs:
            # A tile starting at (fov.x_mm, fov.y_mm) can span up to 4 cells
            col_min = int(math.floor(fov.x_mm / self._cell_size))
            col_max = int(math.floor((fov.x_mm + self._tw) / self._cell_size))
            row_min = int(math.floor(fov.y_mm / self._cell_size))
            row_max = int(math.floor((fov.y_mm + self._th) / self._cell_size))
            for row in range(row_min, row_max + 1):
                for col in range(col_min, col_max + 1):
                    self._grid[(col, row)].append(fov)

    @property
    def total_tiles(self) -> int:
        return len(self._fovs)

    def query(
        self, x_min: float, y_min: float, x_max: float, y_max: float,
    ) -> list[FOVPosition]:
        """Return FOVs whose tile footprint intersects the viewport (mm)."""
        cell_size = self._cell_size

        # Determine which grid cells the viewport overlaps
        col_min = int(math.floor(x_min / cell_size))
        col_max = int(math.floor(x_max / cell_size))
        row_min = int(math.floor(y_min / cell_size))
        row_max = int(math.floor(y_max / cell_size))

        # Collect candidate FOVs from all overlapping cells, deduplicate
        seen: set[int] = set()
        visible: list[FOVPosition] = []
        for row in range(row_min, row_max + 1):
            for col in range(col_min, col_max + 1):
                for fov in self._grid.get((col, row), ()):
                    if fov.fov_index not in seen:
                        # Verify actual intersection (grid cell may contain FOVs
                        # that extend outside the viewport)
                        fx_max = fov.x_mm + self._tw
                        fy_max = fov.y_mm + self._th
                        if (fx_max > x_min and fov.x_mm < x_max
                                and fy_max > y_min and fov.y_mm < y_max):
                            seen.add(fov.fov_index)
                            visible.append(fov)

        return visible

    def bounding_box(self) -> tuple[float, float, float, float]:
        """Return (x_min, y_min, x_max, y_max) of all tiles in mm."""
        if not self._fovs:
            return (0, 0, 0, 0)
        xs = [f.x_mm for f in self._fovs]
        ys = [f.y_mm for f in self._fovs]
        return (min(xs), min(ys), max(xs) + self._tw, max(ys) + self._th)
