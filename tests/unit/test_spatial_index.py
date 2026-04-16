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

    def test_large_grid_performance(self) -> None:
        import time
        fovs = [FOVPosition(fov_index=i, x_mm=(i % 100) * 1.0, y_mm=(i // 100) * 1.0)
                for i in range(10000)]
        region = Region(region_id="big", center_mm=(0, 0, 0), fovs=fovs)
        idx = SpatialIndex(region, tile_width_mm=1.2, tile_height_mm=1.2)
        start = time.perf_counter()
        visible = idx.query(x_min=10, y_min=10, x_max=15, y_max=15)
        elapsed = time.perf_counter() - start
        assert len(visible) < 100  # small viewport, few tiles
        assert elapsed < 0.01  # under 10ms
