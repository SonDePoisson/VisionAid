"""Modèle de coût de déplacement sur la grille, partagé par A*, D* Lite et Dijkstra."""

from __future__ import annotations

import math

import numpy as np

from visionaid.mapping.costmap import UNKNOWN

SQRT2 = math.sqrt(2.0)
# (di, dj, longueur)
MOVES = [
    (-1, 0, 1.0),
    (1, 0, 1.0),
    (0, -1, 1.0),
    (0, 1, 1.0),
    (-1, -1, SQRT2),
    (-1, 1, SQRT2),
    (1, -1, SQRT2),
    (1, 1, SQRT2),
]


def traversal_cost(
    cost: np.ndarray, state: np.ndarray | None, unknown_cost: float, allow_unknown: bool
) -> np.ndarray:
    """Coût par cellule (≥ 0) : proximité + pénalité inconnue ; inf = interdit."""
    c = np.asarray(cost, np.float64).copy()
    if state is not None:
        unk = state == UNKNOWN
        if allow_unknown:
            c[unk & np.isfinite(c)] += unknown_cost
        else:
            c[unk] = np.inf
    return c


def edge_cost(cell_cost: np.ndarray, a: tuple[int, int], b: tuple[int, int]) -> float:
    """Coût d'un pas a → b (voisins) : longueur × (1 + moyenne des coûts des deux cellules).

    Les déplacements diagonaux ne coupent pas les coins occupés.
    """
    ca, cb = cell_cost[a], cell_cost[b]
    if not (math.isfinite(ca) and math.isfinite(cb)):
        return math.inf
    di, dj = b[0] - a[0], b[1] - a[1]
    if di and dj:
        if not (
            math.isfinite(cell_cost[a[0] + di, a[1]]) and math.isfinite(cell_cost[a[0], a[1] + dj])
        ):
            return math.inf
        return SQRT2 * (1.0 + 0.5 * (ca + cb))
    return 1.0 + 0.5 * (ca + cb)


def octile(a: tuple[int, int], b: tuple[int, int]) -> float:
    di, dj = abs(a[0] - b[0]), abs(a[1] - b[1])
    return (di + dj) + (SQRT2 - 2.0) * min(di, dj)


def path_cost(cell_cost: np.ndarray, path: list[tuple[int, int]]) -> float:
    return float(sum(edge_cost(cell_cost, path[k], path[k + 1]) for k in range(len(path) - 1)))
