"""Grille d'occupation 2D vue de dessus (log-odds), gonflage et coût de proximité."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import distance_transform_edt

from visionaid.bus.messages import Costmap

UNKNOWN, FREE, OCC = -1, 0, 1


class OccupancyGrid:
    """Occupation en log-odds dans le repère monde aligné (z haut, sol à z=0), taille dynamique."""

    def __init__(self, cfg_costmap) -> None:
        c = cfg_costmap
        self.res = float(c.resolution_m)
        n = int(round(float(c.init_size_m) / self.res))
        self.L = np.zeros((n, n), np.float32)
        self.origin = np.array([-n * self.res / 2, -n * self.res / 2])
        self.band = tuple(float(v) for v in c.obstacle_band_m)
        self.floor_band = float(c.floor_band_m)
        self.l_occ, self.l_free = float(c.l_occ), float(c.l_free)
        self.l_min, self.l_max = float(c.l_min), float(c.l_max)
        self.p_occ, self.p_free = float(c.occ_threshold), float(c.free_threshold)
        self.half_life = float(c.decay_half_life_s)
        self.radius = float(c.robot_radius_m)
        self.cost_decay = float(c.cost_decay_m)
        self.cost_scale = float(c.cost_scale)
        self.max_range = float(c.max_range_m)
        self.slope = float(getattr(c, "obstacle_height_slope", 0.0))
        self.raycast = bool(c.raycast)
        self.n_updates = 0

    # ------------------------------------------------------------ indexation
    @property
    def shape(self) -> tuple[int, int]:
        return self.L.shape

    def world_to_cell(self, xy: np.ndarray) -> np.ndarray:
        """(N,2) x,y → (N,2) i (ligne, selon y), j (colonne, selon x)."""
        ij = np.floor((np.asarray(xy)[..., ::-1] - self.origin[::-1]) / self.res).astype(int)
        return ij

    def cell_to_world(self, ij: np.ndarray) -> np.ndarray:
        ij = np.asarray(ij, float)
        return np.stack(
            [
                self.origin[0] + (ij[..., 1] + 0.5) * self.res,
                self.origin[1] + (ij[..., 0] + 0.5) * self.res,
            ],
            -1,
        )

    def ensure(self, xy: np.ndarray, margin: float = 1.0) -> None:
        """Agrandit la grille pour contenir les points xy (+ marge)."""
        if len(xy) == 0:
            return
        lo = xy.min(0) - margin
        hi = xy.max(0) + margin
        h, w = self.L.shape
        x0, y0 = self.origin
        x1, y1 = x0 + w * self.res, y0 + h * self.res
        if lo[0] >= x0 and lo[1] >= y0 and hi[0] <= x1 and hi[1] <= y1:
            return
        pad = 2.0
        nx0 = min(x0, lo[0] - pad) if lo[0] < x0 else x0
        ny0 = min(y0, lo[1] - pad) if lo[1] < y0 else y0
        nx1 = max(x1, hi[0] + pad) if hi[0] > x1 else x1
        ny1 = max(y1, hi[1] + pad) if hi[1] > y1 else y1
        dj = int(round((x0 - nx0) / self.res))
        di = int(round((y0 - ny0) / self.res))
        nw = dj + w + int(round((nx1 - x1) / self.res))
        nh = di + h + int(round((ny1 - y1) / self.res))
        L = np.zeros((nh, nw), np.float32)
        L[di : di + h, dj : dj + w] = self.L
        self.L = L
        self.origin = np.array([x0 - dj * self.res, y0 - di * self.res])

    # ---------------------------------------------------------- mise à jour
    def update(self, pts_world: np.ndarray, cam_pos: np.ndarray, dt: float = 1.0 / 30.0) -> None:
        """Intègre un nuage de points (repère monde aligné) vu depuis `cam_pos`.

        Oubli : les log-odds décroissent vers 0 (inconnu) avec une demi-vie `decay_half_life_s`.
        """
        self.n_updates += 1
        if self.half_life > 0 and dt > 0:
            self.L *= np.float32(0.5 ** (dt / self.half_life))
        if len(pts_world) == 0:
            return
        horiz = np.linalg.norm(pts_world[:, :2] - cam_pos[:2], axis=1)
        pts = pts_world[horiz < self.max_range]
        z = pts[:, 2]
        r = horiz[horiz < self.max_range]
        # tolérance croissante avec la distance (bruit de profondeur, inclinaison du sol estimée)
        lo = self.band[0] + self.slope * r
        obst = pts[(z >= lo) & (z <= self.band[1])]
        floor = pts[np.abs(z) < self.floor_band + self.slope * r]
        self.ensure(np.concatenate([pts[:, :2], cam_pos[None, :2]]))
        h, w = self.L.shape
        free_cells = self._cells(floor[:, :2])
        occ_cells = self._cells(obst[:, :2])
        if self.raycast:
            ends = np.concatenate([obst[:, :2], floor[:, :2]])
            ray_cells = self._ray_cells(cam_pos[:2], ends)
            free_cells = (
                np.unique(np.concatenate([free_cells, ray_cells]), axis=0)
                if len(ray_cells)
                else free_cells
            )
        # une cellule touchée par un obstacle n'est pas libérée pendant cette mise à jour
        if len(occ_cells) and len(free_cells):
            occ_lin = occ_cells[:, 0] * w + occ_cells[:, 1]
            free_lin = free_cells[:, 0] * w + free_cells[:, 1]
            free_cells = free_cells[~np.isin(free_lin, occ_lin)]
        if len(free_cells):
            self.L[free_cells[:, 0], free_cells[:, 1]] += self.l_free
        if len(occ_cells):
            self.L[occ_cells[:, 0], occ_cells[:, 1]] += self.l_occ
        np.clip(self.L, self.l_min, self.l_max, out=self.L)

    def _cells(self, xy: np.ndarray) -> np.ndarray:
        if len(xy) == 0:
            return np.zeros((0, 2), int)
        ij = self.world_to_cell(xy)
        h, w = self.L.shape
        ok = (ij[:, 0] >= 0) & (ij[:, 0] < h) & (ij[:, 1] >= 0) & (ij[:, 1] < w)
        return np.unique(ij[ok], axis=0)

    def _ray_cells(self, start: np.ndarray, ends: np.ndarray) -> np.ndarray:
        """Cellules traversées entre la caméra et chaque point (extrémité exclue)."""
        if len(ends) == 0:
            return np.zeros((0, 2), int)
        ends_c = np.unique(self.world_to_cell(ends), axis=0)
        ends = self.cell_to_world(ends_c)
        d = np.linalg.norm(ends - start, axis=1)
        n = np.maximum((d / (0.5 * self.res)).astype(int), 1)
        nmax = int(n.max())
        s = np.arange(nmax)[None, :] / n[:, None]
        valid = s < 1.0 - 1e-9
        pts = start + (ends - start)[:, None, :] * s[..., None]
        cells = self.world_to_cell(pts[valid] if valid.any() else np.zeros((0, 2)))
        # retire la cellule finale de chaque rayon
        return self._cells(self.cell_to_world(cells)) if len(cells) else np.zeros((0, 2), int)

    # ---------------------------------------------------------------- lecture
    def prob(self) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-self.L))

    def state(self) -> np.ndarray:
        p = self.prob()
        s = np.full(p.shape, UNKNOWN, np.int8)
        s[p > self.p_occ] = OCC
        s[p < self.p_free] = FREE
        return s

    def cost(self, state: np.ndarray | None = None) -> np.ndarray:
        """Coût : inf dans le rayon gonflé, décroissance exponentielle au-delà, 0 loin des obstacles."""
        s = self.state() if state is None else state
        occ = s == OCC
        if not occ.any():
            return np.zeros(s.shape, np.float32)
        dist = distance_transform_edt(~occ) * self.res
        c = self.cost_scale * np.exp(
            -np.maximum(dist - self.radius, 0.0) / max(self.cost_decay, 1e-6)
        )
        c = c.astype(np.float32)
        c[dist < self.radius] = np.inf
        return c

    def to_msg(self, t: float, frame_idx: int) -> Costmap:
        s = self.state()
        return Costmap(t, frame_idx, s, self.cost(s), self.origin.copy(), self.res)
