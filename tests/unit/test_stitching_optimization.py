"""Tests for global position optimization."""

import numpy as np

from squid_tools.processing.stitching.optimization import (
    links_from_pairwise_metrics,
    solve_global,
    two_round_optimization,
)


class TestOptimization:
    def test_solve_global_two_tiles(self) -> None:
        links = [{"i": 0, "j": 1, "t": np.array([0.0, 100.0]), "w": 1.0}]
        shifts = solve_global(links, n_tiles=2, fixed_indices=[0])
        assert shifts.shape == (2, 2)
        assert np.isclose(shifts[0, 1], 0.0)  # tile 0 fixed
        assert np.isclose(shifts[1, 1], 100.0)  # tile 1 at dx=100

    def test_links_from_pairwise_metrics(self) -> None:
        metrics = {(0, 1): (5, 10, 0.95)}
        links = links_from_pairwise_metrics(metrics)
        assert len(links) == 1
        assert links[0]["i"] == 0
        assert links[0]["j"] == 1
        assert np.isclose(links[0]["t"][0], 5.0)
        assert np.isclose(links[0]["t"][1], 10.0)

    def test_two_round_optimization(self) -> None:
        links = [
            {"i": 0, "j": 1, "t": np.array([0.0, 100.0]), "w": 1.0},
            {"i": 1, "j": 2, "t": np.array([0.0, 100.0]), "w": 1.0},
        ]
        shifts = two_round_optimization(
            links,
            n_tiles=3,
            fixed_indices=[0],
            rel_thresh=3.0,
            abs_thresh=50.0,
            iterative=False,
        )
        assert shifts.shape == (3, 2)
        assert np.isclose(shifts[2, 1], 200.0, atol=1.0)
