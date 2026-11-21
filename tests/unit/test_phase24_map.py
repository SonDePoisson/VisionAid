"""Phase 24 (B) : carte fiable — obstacles à portée fiable, trajectoire de l'utilisateur libre."""

from __future__ import annotations

import numpy as np
import pytest

from visionaid.mapping.costmap import FREE, OCC, OccupancyGrid
from visionaid.utils.config import load_config

pytestmark = pytest.mark.unit


def grid(**ov):
    return OccupancyGrid(load_config(overrides={f"costmap.{k}": v for k, v in ov.items()}).costmap)


def wall(x, y0=-1.0, y1=1.0, n=400):
    ys = np.linspace(y0, y1, n)
    return np.stack([np.full(n, x), ys, np.full(n, 0.8)], 1)


def test_far_points_do_not_create_obstacles():
    g = grid(occ_range_m=3.0)
    cam = np.array([0.0, 0.0, 1.4])
    for _ in range(10):
        g.update(np.concatenate([wall(2.0), wall(4.0)]), cam, 0.1)
    st = g.state()
    near = g.world_to_cell(np.array([[2.0, 0.0]]))[0]
    far = g.world_to_cell(np.array([[4.0, 0.0]]))[0]
    assert st[tuple(near)] == OCC  # à 2 m : obstacle marqué
    assert st[tuple(far)] != OCC  # à 4 m : pas d'obstacle (hors portée fiable)


def test_walked_cells_are_free_and_never_blocked():
    g = grid(occ_range_m=3.0)
    cam = np.array([0.0, 0.0, 1.4])
    # obstacle bruité juste à côté de la trajectoire
    obs = np.array([[0.25, 0.0, 0.8]] * 50)
    for _ in range(10):
        g.update(obs, cam, 0.1)
    c0 = g.cost()
    me = tuple(g.world_to_cell(np.array([[0.0, 0.0]]))[0])
    assert not np.isfinite(c0[me])  # dans la marge de 0,35 m : bloqué
    g.carve(np.array([0.0, 0.0]), 0.20)
    g.update(obs, cam, 0.1)
    assert g.state()[me] == FREE
    assert np.isfinite(g.cost()[me])  # là où l'on est passé : jamais infranchissable
    # l'obstacle lui-même reste un obstacle
    ob = tuple(g.world_to_cell(np.array([[0.25, 0.0]]))[0])
    assert g.state()[ob] == OCC


def test_walked_mask_survives_grid_growth():
    g = grid()
    g.carve(np.array([0.0, 0.0]), 0.2)
    n0 = int(g.walked.sum())
    g.ensure(np.array([[20.0, 20.0]]))  # agrandissement de la grille
    assert g.walked.shape == g.L.shape and int(g.walked.sum()) == n0
    me = tuple(g.world_to_cell(np.array([[0.0, 0.0]]))[0])
    assert g.walked[me]


def test_obstacle_appearing_on_walked_cells_is_seen():
    """Sécurité : une chaise posée là où l'utilisateur est passé doit réapparaître sur la carte."""
    g = grid(occ_range_m=3.0)
    cam = np.array([0.0, 0.0, 1.4])
    g.carve(np.array([1.0, 0.0]), 0.20)  # passage en (1, 0)
    g.carve(np.array([0.0, 0.0]), 0.20)
    chair = np.array([[1.0, 0.0, 0.5]] * 50)
    for _ in range(10):
        g.update(chair, cam, 0.1)
    cell = tuple(g.world_to_cell(np.array([[1.0, 0.0]]))[0])
    assert g.walked[cell]
    assert g.state()[cell] == OCC
    assert not np.isfinite(g.cost()[cell])  # infranchissable malgré le passage
