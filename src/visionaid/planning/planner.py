"""Planificateur de haut niveau : costmap + position utilisateur + objet → Path."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.ndimage import distance_transform_edt

from visionaid.bus.messages import Costmap, ObjectEstimate, Path
from visionaid.mapping.costmap import FREE
from visionaid.planning.astar import astar
from visionaid.planning.dstar_lite import DStarLite
from visionaid.planning.grid import traversal_cost
from visionaid.planning.lookahead import lookahead_point, polyline_length, smooth_path


def cell_of(xy: np.ndarray, origin: np.ndarray, res: float) -> tuple[int, int]:
    return int(np.floor((xy[1] - origin[1]) / res)), int(np.floor((xy[0] - origin[0]) / res))


def world_of(ij: tuple[int, int], origin: np.ndarray, res: float) -> np.ndarray:
    return np.array([origin[0] + (ij[1] + 0.5) * res, origin[1] + (ij[0] + 0.5) * res])


def nearest_passable(
    cc: np.ndarray,
    ij: tuple[int, int],
    radius_cells: int,
    prefer: np.ndarray | None = None,
    toward: tuple[int, int] | None = None,
) -> tuple[int, int] | None:
    """Cellule franchissable la plus proche de ij (dans un rayon), en préférant `prefer` (ex. libre).

    À distance égale (à une cellule près), on départage par la proximité de `toward` (l'utilisateur).
    """
    h, w = cc.shape
    i0, j0 = ij
    r = radius_cells
    a0, a1 = max(i0 - r, 0), min(i0 + r + 1, h)
    b0, b1 = max(j0 - r, 0), min(j0 + r + 1, w)
    if a0 >= a1 or b0 >= b1:
        return None
    sub = np.isfinite(cc[a0:a1, b0:b1])
    for mask in ([sub & prefer[a0:a1, b0:b1]] if prefer is not None else []) + [sub]:
        if not mask.any():
            continue
        ii, jj = np.nonzero(mask)
        d = np.sqrt((ii + a0 - i0) ** 2 + (jj + b0 - j0) ** 2)
        if d.min() > r:
            continue
        cand = d <= d.min() + 1.0
        if toward is not None:
            du = (ii + a0 - toward[0]) ** 2 + (jj + b0 - toward[1]) ** 2
            k = int(np.argmin(np.where(cand, du, np.inf)))
        else:
            k = int(np.argmin(d))
        return int(ii[k] + a0), int(jj[k] + b0)
    return None


class Planner:
    """Choisit le but (cellule libre la plus proche de l'objet), planifie (A* ou D* Lite), lisse."""

    def __init__(self, cfg) -> None:
        p = cfg.planning
        self.algorithm = str(p.algorithm)
        self.unknown_cost = float(p.unknown_cost)
        self.allow_unknown = bool(p.allow_unknown)
        self.lookahead_m = float(p.lookahead_m)
        self.search_r = float(p.target_search_radius_m)
        self.body_clearance = float(cfg.guidance.obstacle_corridor_m)
        self.dstar: DStarLite | None = None
        self._dkey = None
        self.n_plans = 0
        self.n_fail = 0

    def plan(self, cm: Costmap, user_xy: np.ndarray, obj: ObjectEstimate) -> Path:
        t, idx = cm.t, cm.frame_idx
        empty = Path(t, idx, np.zeros((0, 2)), np.full(2, np.nan), np.full(2, np.nan), False, 0.0)
        if obj is None or not np.isfinite(obj.position).all():
            return empty
        cc = traversal_cost(cm.cost, cm.state, self.unknown_cost, self.allow_unknown)
        res, origin = cm.resolution, cm.origin
        h, w = cc.shape
        s_ij = cell_of(user_xy, origin, res)
        o_ij = cell_of(obj.position[:2], origin, res)
        if not (0 <= s_ij[0] < h and 0 <= s_ij[1] < w):
            return empty
        o_ij = (int(np.clip(o_ij[0], 0, h - 1)), int(np.clip(o_ij[1], 0, w - 1)))
        goal = nearest_passable(cc, o_ij, int(self.search_r / res), cm.state == FREE, toward=s_ij)
        if goal is None:
            self.n_fail += 1
            return empty
        start = s_ij
        if not np.isfinite(cc[start]):
            # l'utilisateur est dans une zone gonflée (bruit, meuble proche) : on part de la
            # cellule franchissable la plus proche
            start = nearest_passable(cc, s_ij, int(1.0 / res))
            if start is None:
                self.n_fail += 1
                return empty
        self.n_plans += 1
        if self.algorithm == "dstar":
            key = (cc.shape, tuple(np.round(origin, 6)), goal)
            if self.dstar is None or key != self._dkey:
                self.dstar = DStarLite(cc, goal)
                self._dkey = key
            else:
                self.dstar.set_costs(cc)
            cells, _cost = self.dstar.plan(start)
        else:
            cells, _cost = astar(cc, start, goal)
        if cells is None:
            self.n_fail += 1
            return empty
        cells = smooth_path(cc, cells)
        pts = np.array([world_of(c, origin, res) for c in cells])
        pts = (
            np.vstack([user_xy[None, :2], pts[1:]])
            if len(pts) > 1
            else np.vstack([user_xy[None, :2], pts])
        )
        goal_xy = world_of(goal, origin, res)
        la = self._lookahead_los(cm, pts, s_ij, start, origin, res)
        return Path(t, idx, pts, la, goal_xy, True, polyline_length(pts))

    def _lookahead_los(self, cm: Costmap, pts, user_ij, start, origin, res) -> np.ndarray:
        """Point d'anticipation le plus loin (≤ lookahead_m) en ligne de vue de l'utilisateur.

        La ligne de vue est testée depuis la position réelle sur une grille où seules les cellules
        à moins de `body_clearance_m` d'un obstacle sont bloquantes : la direction donnée ne mène
        jamais droit sur un obstacle, même quand l'utilisateur a dérivé hors du chemin. Sans
        cette contrainte, la corde vers un point situé après un virage coupe le coin.
        """
        from visionaid.planning.lookahead import line_of_sight

        clear = distance_to_obstacles(cm.state, res)
        body = np.where(clear >= self.body_clearance, 0.0, np.inf)
        h, w = body.shape
        src = user_ij if np.isfinite(body[user_ij]) else start
        d = self.lookahead_m
        while d > 0.15:
            p = lookahead_point(pts, d)
            ij = cell_of(p, origin, res)
            if 0 <= ij[0] < h and 0 <= ij[1] < w and line_of_sight(body, src, ij):
                return p
            d -= 0.1
        # aucune visée sûre : on rejoint d'abord la cellule dégagée du départ
        return world_of(start, origin, res) if start != user_ij else lookahead_point(pts, 0.3)

    # interface Block du bus
    def process(self, inputs: dict[str, Any]) -> dict[str, Any] | None:
        cm, obj, pose = inputs.get("costmap"), inputs.get("object"), inputs.get("pose_world")
        if cm is None or obj is None or pose is None:
            return None
        return {"path": self.plan(cm, pose.T_world_cam[:2, 3], obj)}


def distance_to_obstacles(state: np.ndarray, res: float) -> np.ndarray:
    from visionaid.mapping.costmap import OCC

    occ = state == OCC
    return distance_transform_edt(~occ) * res if occ.any() else np.full(state.shape, np.inf)
