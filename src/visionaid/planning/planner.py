"""Planificateur de haut niveau : costmap + position utilisateur + objet → Path."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.ndimage import distance_transform_edt

from visionaid.bus.messages import Costmap, ObjectEstimate, Path
from visionaid.mapping.costmap import FREE, OCC, UNKNOWN
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
        # pas de chemin connu jusqu'à l'objet : chemin jusqu'à la limite de la zone connue
        self.frontier_fallback = bool(getattr(p, "frontier_fallback", True))
        self.n_frontier = 0
        self.lookahead_m = float(p.lookahead_m)
        self.search_r = float(p.target_search_radius_m)
        self.body_clearance = float(cfg.guidance.obstacle_corridor_m)
        self.dstar: DStarLite | None = None
        self._dkey = None
        self.n_plans = 0
        self.n_fail = 0
        # stabilité (phase 25) : engagement sur le chemin précédent, visée vers l'objet au but
        self.commit_ratio = float(getattr(p, "commit_ratio", 0.0) or 0.0)
        self.commit_margin = float(getattr(p, "commit_margin_m", 0.0) or 0.0)
        self.near_goal = float(getattr(p, "near_goal_m", 0.0) or 0.0)
        self.prev_pts: np.ndarray | None = None
        self.prev_goal: np.ndarray | None = None
        self.n_kept = 0
        # approche de l'objet (phase 27) : but « à portée de main » le plus rapide à atteindre,
        # marge réduite près de l'objet (passer entre deux chaises pour attraper la gourde)
        self.reach = float(getattr(p, "reach_m", 0.0) or 0.0)
        self.zone = float(getattr(p, "approach_zone_m", 0.0) or 0.0)
        self.zone_clear = float(getattr(p, "approach_clearance_m", 0.0) or 0.0)
        self.zone_penalty = float(getattr(p, "approach_penalty", 3.0))
        self.goal_keep = float(getattr(p, "goal_keep_ratio", 0.15))
        self.n_reach_goal = 0
        self.detour_ratio = float(getattr(p, "approach_detour_ratio", 1.5))
        self.detour_slack = float(getattr(p, "approach_detour_slack_m", 1.0))
        self.n_relaxed = 0

    def plan(self, cm: Costmap, user_xy: np.ndarray, obj: ObjectEstimate) -> Path:
        """Chemin vers l'objet par des zones **connues** (vues libres) uniquement.

        Sans `allow_unknown`, une zone jamais vue n'est jamais proposée, même plus courte. Si
        aucun chemin connu n'atteint l'objet (carte encore partielle), le chemin s'arrête à la
        limite de la zone connue, sur le meilleur trajet estimé (`frontier_fallback`) : on y
        va, la carte s'étend, et le chemin complet apparaît.
        """
        t, idx = cm.t, cm.frame_idx
        empty = Path(t, idx, np.zeros((0, 2)), np.full(2, np.nan), np.full(2, np.nan), False, 0.0)
        if obj is None or not np.isfinite(obj.position).all():
            return empty
        res, origin = cm.resolution, cm.origin
        cc_known = traversal_cost(cm.cost, cm.state, self.unknown_cost, self.allow_unknown)
        h, w = cc_known.shape
        s_ij = cell_of(user_xy, origin, res)
        o_ij = cell_of(obj.position[:2], origin, res)
        if not (0 <= s_ij[0] < h and 0 <= s_ij[1] < w):
            return empty
        o_ij = (int(np.clip(o_ij[0], 0, h - 1)), int(np.clip(o_ij[1], 0, w - 1)))
        found = self._search(cm, cc_known, s_ij, o_ij, obj, self.allow_unknown)
        frontier = False
        if found is None and not self.allow_unknown and self.frontier_fallback:
            cc_unk = traversal_cost(cm.cost, cm.state, self.unknown_cost, True)
            found = self._search(cm, cc_unk, s_ij, o_ij, obj, True)
            if found is not None:
                goal, cells, start, _ = found
                cells = self._cut_at_unknown(cm.state, cells)
                if cells is None:
                    found = None
                else:
                    found = (cells[-1], cells, start, cc_known)
                    frontier = True
                    self.n_frontier += 1
        if found is None:
            self.n_fail += 1
            return empty
        goal, cells, start, cc = found
        self.n_plans += 1
        cells = smooth_path(cc, cells)
        pts = np.array([world_of(c, origin, res) for c in cells])
        pts = (
            np.vstack([user_xy[None, :2], pts[1:]])
            if len(pts) > 1
            else np.vstack([user_xy[None, :2], pts])
        )
        goal_xy = world_of(goal, origin, res)
        kept = self._keep_previous(cc, origin, res, user_xy[:2], goal_xy, polyline_length(pts))
        if kept is not None:
            pts = kept
            goal_xy = kept[-1].copy()  # le but publié est la fin du chemin réellement suivi
            self.n_kept += 1
        self.prev_pts, self.prev_goal = pts.copy(), goal_xy.copy()
        length = polyline_length(pts)
        if not frontier and self.near_goal > 0 and length < self.near_goal:
            # au but : la direction d'un point à quelques centimètres n'a plus de sens, on vise
            # l'objet lui-même (stable), comme le fait le guidage en fin d'approche
            la = np.asarray(obj.position[:2], float).copy()
        else:
            la = self._lookahead_los(cm, pts, s_ij, start, origin, res)
        return Path(t, idx, pts, la, goal_xy, True, length)

    def _search(self, cm, cc, s_ij, o_ij, obj, allow_unknown: bool):
        """But et cellules du chemin sur la grille de coûts `cc` ; (but, cellules, départ, cc)
        ou None."""
        res, origin = cm.resolution, cm.origin
        d_obj = None
        strict = np.isfinite(cc)  # franchissable avec la marge normale
        cc_strict = cc
        if self.zone > 0 and self.zone_clear > 0:
            cc, d_obj = self._relax_near_object(cm, cc, obj, res, origin, allow_unknown)
        goal = nearest_passable(cc, o_ij, int(self.search_r / res), cm.state == FREE, toward=s_ij)
        if goal is None:
            return None
        start = s_ij
        if not np.isfinite(cc[start]):
            # l'utilisateur est dans une zone gonflée (bruit, meuble proche) ou pas encore
            # cartographiée : on part de la cellule franchissable la plus proche
            start = nearest_passable(cc, s_ij, int(1.0 / res))
            if start is None:
                return None
        cells = None
        if self.reach > 0:
            reach = self._reach_goal(cc, start, obj, res, origin, d_obj, strict)
            if reach is not None and cc is not cc_strict and np.isfinite(cc_strict[start]):
                # la marge réduite ne sert que si elle évite un vrai détour : sinon on garde le
                # chemin avec la marge normale (contournement d'un obstacle surgissant, etc.)
                normal = self._reach_goal(cc_strict, start, obj, res, origin, d_obj, strict)
                if normal is not None:
                    ln = len(normal[1]) * res
                    lr = len(reach[1]) * res
                    if ln <= self.detour_ratio * lr + self.detour_slack:
                        reach = normal
                        cc = cc_strict
                    else:
                        self.n_relaxed += 1
            if reach is not None:
                goal, cells = reach
                self.n_reach_goal += 1
        if cells is None:
            if self.algorithm == "dstar" and not (allow_unknown and not self.allow_unknown):
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
            return None
        return goal, cells, start, cc

    def _cut_at_unknown(self, state, cells):
        """Coupe le chemin à la première cellule inconnue (après les cellules de départ) ; None
        s'il ne reste rien d'utile (< 2 cellules connues)."""
        k = 0
        while k < len(cells) and state[cells[k]] == UNKNOWN:  # départ pas encore cartographié
            k += 1
        e = k
        while e < len(cells) and state[cells[e]] != UNKNOWN:
            e += 1
        out = cells[:e]
        return out if e - k >= 2 else None

    def _relax_near_object(self, cm, cc, obj, res, origin, allow_unknown: bool = True):
        """Près de l'objet (≤ `approach_zone_m`), la marge passe de `robot_radius_m` à
        `approach_clearance_m` (demi-largeur du corps). Ces cellules restent plus coûteuses
        (`approach_penalty`) : on ne s'y engage que si cela raccourcit vraiment le trajet."""
        h, w = cc.shape
        jj, ii = np.meshgrid(np.arange(w), np.arange(h))
        xs = origin[0] + (jj + 0.5) * res
        ys = origin[1] + (ii + 0.5) * res
        d_obj = np.hypot(xs - obj.position[0], ys - obj.position[1])
        clear = distance_to_obstacles(cm.state, res)
        relax = (
            ~np.isfinite(cc) & (cm.state != OCC) & (clear >= self.zone_clear) & (d_obj <= self.zone)
        )
        if not allow_unknown:  # la marge réduite ne rend jamais franchissable une zone inconnue
            relax &= cm.state != UNKNOWN
        if relax.any():
            cc = cc.copy()
            cc[relax] = self.zone_penalty + np.where(cm.state[relax] < 0, self.unknown_cost, 0.0)
        return cc, d_obj

    def _reach_goal(self, cc, start, obj, res, origin, d_obj, strict=None):
        """But « à portée de main » : parmi les cellules franchissables à moins de `reach_m` de
        l'objet (on attrape une gourde posée sur une table depuis le bord, pas besoin d'en faire
        le tour), celle dont le trajet depuis l'utilisateur est le moins coûteux. Hystérésis :
        le but précédent est conservé s'il reste à moins de +15 % du meilleur.
        Renvoie (but, chemin) ou None (repli sur le but « cellule la plus proche »)."""
        from visionaid.planning.astar import _astar_kernel

        h, w = cc.shape
        if d_obj is None:
            jj, ii = np.meshgrid(np.arange(w), np.arange(h))
            d_obj = np.hypot(
                origin[0] + (jj + 0.5) * res - obj.position[0],
                origin[1] + (ii + 0.5) * res - obj.position[1],
            )
        cand = (d_obj <= self.reach) & np.isfinite(cc)
        if not cand.any():
            return None
        flat = np.ascontiguousarray(cc, np.float64).ravel()
        s = start[0] * w + start[1]
        g, parent = _astar_kernel(flat, h, w, s, -1, False)  # coûts depuis l'utilisateur
        g = g.reshape(h, w)
        # le but garde la marge normale s'il existe une telle cellule atteignable à portée de
        # main ; il n'entre dans la bande à marge réduite qu'à défaut (objet au milieu d'une
        # table). Sans cette préférence, l'agent du simulateur finissait collé au meuble.
        if strict is not None:
            pref = cand & strict & np.isfinite(g)
            if pref.any():
                cand = pref
        score = np.where(cand, g + 3.0 * d_obj / res, np.inf)  # à coût égal, près de l'objet
        k = int(np.argmin(score))
        if not np.isfinite(score.flat[k]):
            return None
        goal = (k // w, k % w)
        if self.prev_goal is not None:
            pg = cell_of(self.prev_goal, origin, res)
            if 0 <= pg[0] < h and 0 <= pg[1] < w and np.isfinite(score[pg]):
                if score[pg] <= score.flat[k] * (1.0 + self.goal_keep) + 2.0:
                    goal = pg
        cells = []
        u = goal[0] * w + goal[1]
        while u != -1:
            cells.append((int(u // w), int(u % w)))
            u = int(parent[u])
        cells.reverse()
        return goal, cells

    def _keep_previous(self, cc, origin, res, user_xy, goal_xy, new_len) -> np.ndarray | None:
        """Chemin précédent, raccourci depuis l'utilisateur, s'il reste praticable et pas
        nettement plus long que le nouveau (évite l'alternance entre deux contournements
        presque équivalents sur une carte bruitée). None sinon."""
        self.keep_why = "pas de chemin précédent"
        if self.commit_ratio <= 0 or self.prev_pts is None or len(self.prev_pts) < 2:
            return None
        self.keep_why = "but déplacé"
        if np.linalg.norm(goal_xy - self.prev_goal) > 0.15:
            # but déplacé (même de peu) : nouveau chemin. Sinon le chemin gardé finirait à
            # l'ancien but pendant que le guidage compare la position au nouveau (agent bloqué
            # en approche dans le simulateur, couloir : 94 % → 67 % de succès)
            return None
        prev = self.prev_pts
        # point du chemin précédent le plus proche de l'utilisateur (projection sur les segments)
        best, best_k, best_p = np.inf, 0, prev[0]
        for k in range(len(prev) - 1):
            a, b = prev[k], prev[k + 1]
            ab = b - a
            u = float(np.clip(np.dot(user_xy - a, ab) / max(np.dot(ab, ab), 1e-12), 0.0, 1.0))
            p = a + u * ab
            d = float(np.linalg.norm(user_xy - p))
            if d < best:
                best, best_k, best_p = d, k, p
        self.keep_why = "écarté du chemin"
        if best > 0.5:
            return None  # l'utilisateur s'est écarté du chemin précédent
        rest = np.vstack([user_xy[None], best_p[None], prev[best_k + 1 :]])
        rest = rest[np.r_[True, np.linalg.norm(np.diff(rest, axis=0), axis=1) > 1e-6]]
        h, w = cc.shape
        self.keep_why = "bloqué"
        for a, b in zip(rest[:-1], rest[1:], strict=True):  # praticable sur la nouvelle carte
            n = max(int(np.linalg.norm(b - a) / (0.5 * res)), 1)
            for s_ in np.linspace(0.0, 1.0, n + 1):
                i, j = cell_of(a + s_ * (b - a), origin, res)
                if not (0 <= i < h and 0 <= j < w) or not np.isfinite(cc[i, j]):
                    return None
        self.keep_why = "trop long"
        if polyline_length(rest) > new_len * (1.0 + self.commit_ratio) + self.commit_margin:
            return None
        self.keep_why = "gardé"
        return rest

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
        if not self.allow_unknown:  # la visée ne coupe pas non plus par une zone jamais vue
            body[cm.state == UNKNOWN] = np.inf
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
