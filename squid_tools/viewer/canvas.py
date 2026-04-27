"""Vispy stage canvas in mm coordinates.

Receives VisibleTile objects from the viewport engine and renders them.
Pan/zoom operates in mm. Borders drawn on top.

The old VispyCanvas class is kept for backward compatibility.
"""

from __future__ import annotations

import numpy as np
import vispy.app
from PySide6.QtCore import QObject, Signal
from vispy.scene import SceneCanvas
from vispy.scene.cameras import PanZoomCamera
from vispy.scene.visuals import Image, Line
from vispy.visuals.transforms import STTransform

from squid_tools.viewer.viewport_engine import VisibleTile

vispy.app.use_app("pyside6")


def _to_float32(data: np.ndarray) -> np.ndarray:
    """Convert to float32 without normalizing. Let clim handle the range."""
    if data.dtype == np.float32:
        return data
    return data.astype(np.float32)


class StageCanvas(QObject):
    """Renders tiles in mm stage coordinates."""

    selection_drawn = Signal(tuple)  # (x_min_mm, y_min_mm, x_max_mm, y_max_mm)

    def __init__(self) -> None:
        super().__init__()
        self._canvas = SceneCanvas(keys="interactive", show=False, bgcolor="#000000")
        self._view = self._canvas.central_widget.add_view()
        self._view.camera = PanZoomCamera(aspect=1)

        self._tiles: dict[int, Image] = {}      # fov_index -> Image
        self._borders: dict[int, Line] = {}      # fov_index -> Line
        self._borders_visible = False
        self._clim: tuple[float, float] | None = None
        self._cmap: str = "grays"

        # Selection state (canvas just tracks IDs; ViewerWidget owns real state)
        self._selected_ids: set[int] = set()

        # Drag-box state
        self._drag_start: tuple[float, float] | None = None
        self._drag_rect: Line | None = None

        # Wire mouse events
        self._canvas.events.mouse_press.connect(self._on_mouse_press)
        self._canvas.events.mouse_move.connect(self._on_mouse_move)
        self._canvas.events.mouse_release.connect(self._on_mouse_release)

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
            transform = STTransform(
                scale=(sx, sy, 1), translate=(tile.x_mm, tile.y_mm, 0),
            )

            # RGB composite (H, W, 3): no colormap, clim=(0, 1)
            # Grayscale (H, W): use colormap and clim
            is_rgb = data.ndim == 3 and data.shape[2] in (3, 4)
            if is_rgb:
                clim = (0.0, 1.0)
                cmap = "grays"  # ignored for RGB but vispy requires it
            else:
                clim = self._clim or (float(data.min()), float(data.max()))
                cmap = self._cmap

            if tile.fov_index in self._tiles:
                self._tiles[tile.fov_index].set_data(data)
                self._tiles[tile.fov_index].transform = transform
                self._tiles[tile.fov_index].clim = clim
            else:
                img = Image(
                    data, cmap=cmap, clim=clim,
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

        color = self._border_color_for(tile.fov_index, self._selected_ids)
        if tile.fov_index in self._borders:
            self._borders[tile.fov_index].set_data(pos=corners, color=color)
        else:
            line = Line(
                pos=corners, color=color, width=2,
                connect="strip", parent=self._view.scene,
            )
            line.order = -1
            self._borders[tile.fov_index] = line

        self._borders[tile.fov_index].visible = self._borders_visible

    def set_selected_ids(self, ids: set[int]) -> None:
        """Update which FOVs should be drawn with selection borders."""
        self._selected_ids = set(ids)
        # Re-color existing borders
        for fov_id, line in self._borders.items():
            color = self._border_color_for(fov_id, self._selected_ids)
            line.set_data(color=color)

    @staticmethod
    def _border_color_for(fov_index: int, selected_ids: set[int]) -> str:
        """Return the border color string for a given FOV."""
        return "#2A82DA" if fov_index in selected_ids else "yellow"

    def _scene_coords(self, event_pos: tuple[float, float]) -> tuple[float, float]:
        """Convert pixel event coords to scene (mm) coords."""
        tr = self._canvas.scene.node_transform(self._view.scene)
        mapped = tr.map(event_pos)
        return float(mapped[0]), float(mapped[1])

    def _on_mouse_press(self, event: object) -> None:
        modifiers = getattr(event, "modifiers", ())
        from vispy.util.keys import SHIFT
        if SHIFT in modifiers:
            self._drag_start = self._scene_coords(event.pos)
            # Disable camera interaction while drag-selecting
            self._view.camera.interactive = False

    def _on_mouse_move(self, event: object) -> None:
        if self._drag_start is None:
            return
        x0, y0 = self._drag_start
        x1, y1 = self._scene_coords(event.pos)
        self._update_drag_rect(x0, y0, x1, y1)

    def _on_mouse_release(self, event: object) -> None:
        if self._drag_start is None:
            return
        x0, y0 = self._drag_start
        x1, y1 = self._scene_coords(event.pos)
        x_min, x_max = min(x0, x1), max(x0, x1)
        y_min, y_max = min(y0, y1), max(y0, y1)
        # Remove the drag rectangle visual
        if self._drag_rect is not None:
            self._drag_rect.parent = None
            self._drag_rect = None
        self._drag_start = None
        self._view.camera.interactive = True
        # Emit selection bounds
        self.selection_drawn.emit((x_min, y_min, x_max, y_max))

    def _update_drag_rect(
        self, x0: float, y0: float, x1: float, y1: float,
    ) -> None:
        corners = np.array([
            [x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0],
        ], dtype=np.float32)
        if self._drag_rect is None:
            self._drag_rect = Line(
                pos=corners, color="#2A82DA", width=1,
                connect="strip", parent=self._view.scene,
            )
            self._drag_rect.order = -2
        else:
            self._drag_rect.set_data(pos=corners)

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


# ---------------------------------------------------------------------------
# Legacy VispyCanvas kept for backward compatibility with existing tests.
# New code should use StageCanvas + ViewportEngine.
# ---------------------------------------------------------------------------

class VispyCanvas:
    """2D microscopy canvas in millimeter coordinate space.

    .. deprecated::
        Use StageCanvas with ViewportEngine instead.
    """

    def __init__(self) -> None:
        self._canvas = SceneCanvas(keys="interactive", show=False)
        self._view = self._canvas.central_widget.add_view()
        self._view.camera = PanZoomCamera(aspect=1)

        self._main_image: Image | None = None
        self._tiles: dict[str, Image] = {}
        self._tile_bounds: dict[str, tuple[float, float, float, float]] = {}
        self._borders: dict[str, Line] = {}
        self._borders_visible = False
        self._global_clim: tuple[float, float] | None = None

    def set_global_clim(self, clim: tuple[float, float]) -> None:
        self._global_clim = clim
        if self._main_image is not None:
            self._main_image.clim = clim
        for tile in self._tiles.values():
            tile.clim = clim

    def set_image(
        self,
        data: np.ndarray,
        cmap: str = "grays",
        clim: tuple[float, float] | None = None,
    ) -> None:
        normalized = _to_float32(data)
        if clim is None:
            if self._global_clim is not None:
                clim = self._global_clim
            else:
                clim = (float(normalized.min()), float(normalized.max()))

        if self._main_image is not None:
            self._main_image.set_data(normalized)
            self._main_image.cmap = cmap
            self._main_image.clim = clim
        else:
            self._main_image = Image(
                normalized, cmap=cmap, clim=clim, parent=self._view.scene
            )

    def has_image(self) -> bool:
        return self._main_image is not None or len(self._tiles) > 0

    def add_tile(
        self,
        data: np.ndarray,
        x_mm: float,
        y_mm: float,
        width_mm: float,
        height_mm: float,
        tile_id: str,
        cmap: str = "grays",
        clim: tuple[float, float] | None = None,
    ) -> None:
        normalized = _to_float32(data)
        if clim is None:
            if self._global_clim is not None:
                clim = self._global_clim
            else:
                clim = (float(normalized.min()), float(normalized.max()))

        h_px, w_px = normalized.shape[:2]
        self._tile_bounds[tile_id] = (x_mm, y_mm, width_mm, height_mm)

        sx = width_mm / w_px if w_px > 0 else 1.0
        sy = height_mm / h_px if h_px > 0 else 1.0
        transform = STTransform(scale=(sx, sy, 1), translate=(x_mm, y_mm, 0))

        if tile_id in self._tiles:
            self._tiles[tile_id].set_data(normalized)
            self._tiles[tile_id].transform = transform
        else:
            img = Image(normalized, cmap=cmap, clim=clim, parent=self._view.scene)
            img.transform = transform
            self._tiles[tile_id] = img

    def tile_count(self) -> int:
        return len(self._tiles)

    def get_tile_at(self, x: float, y: float) -> str | None:
        for tile_id, (tx, ty, tw, th) in self._tile_bounds.items():
            if tx <= x <= tx + tw and ty <= y <= ty + th:
                return tile_id
        return None

    def add_border(
        self,
        x_mm: float,
        y_mm: float,
        width_mm: float,
        height_mm: float,
        border_id: str,
        color: str = "yellow",
    ) -> None:
        corners = np.array(
            [
                [x_mm, y_mm],
                [x_mm + width_mm, y_mm],
                [x_mm + width_mm, y_mm + height_mm],
                [x_mm, y_mm + height_mm],
                [x_mm, y_mm],
            ],
            dtype=np.float32,
        )

        if border_id in self._borders:
            self._borders[border_id].set_data(pos=corners, color=color)
        else:
            line = Line(
                pos=corners, color=color, width=2,
                connect="strip", parent=self._view.scene,
            )
            line.order = -1
            self._borders[border_id] = line

    def border_count(self) -> int:
        return len(self._borders)

    def set_borders_visible(self, visible: bool) -> None:
        self._borders_visible = visible
        for border in self._borders.values():
            border.visible = visible

    def update_border_color(self, border_id: str, color: str) -> None:
        if border_id in self._borders:
            self._borders[border_id].set_data(color=color)

    def clear_images(self) -> None:
        if self._main_image is not None:
            self._main_image.parent = None
            self._main_image = None

        for tile in self._tiles.values():
            tile.parent = None
        self._tiles.clear()
        self._tile_bounds.clear()

        for border in self._borders.values():
            border.parent = None
        self._borders.clear()

    def fit_view(self) -> None:
        self._view.camera.set_range()

    def native_widget(self) -> object:
        return self._canvas.native

    def get_viewport_bounds(self) -> tuple[float, float, float, float]:
        rect = self._view.camera.rect
        return (rect.left, rect.bottom, rect.right, rect.top)
