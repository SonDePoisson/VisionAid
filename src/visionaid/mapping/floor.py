"""Estimation et suivi du plan du sol ; alignement du repère monde (z vers le haut)."""

from __future__ import annotations

import numpy as np

from visionaid.mapping.geometry import backproject, make_T, transform


def fit_plane_ransac(
    pts: np.ndarray,
    iters: int,
    inlier_dist: float,
    rng: np.random.Generator,
    up_hint: np.ndarray | None = None,
    max_tilt_deg: float = 90.0,
) -> tuple[np.ndarray, float, np.ndarray] | None:
    """Plan n·p + d = 0 par RANSAC puis moindres carrés sur les inliers. Retourne (n, d, masque)."""
    if len(pts) < 3:
        return None
    best_inl, best = None, None
    cos_max = np.cos(np.radians(max_tilt_deg))
    for _ in range(iters):
        s = pts[rng.choice(len(pts), 3, replace=False)]
        n = np.cross(s[1] - s[0], s[2] - s[0])
        nn = np.linalg.norm(n)
        if nn < 1e-9:
            continue
        n /= nn
        if up_hint is not None:
            if np.dot(n, up_hint) < 0:
                n = -n
            if np.dot(n, up_hint) < cos_max:
                continue
        d = -float(np.dot(n, s[0]))
        inl = np.abs(pts @ n + d) < inlier_dist
        if best_inl is None or inl.sum() > best_inl.sum():
            best_inl, best = inl, (n, d)
    if best is None:
        return None
    P = pts[best_inl]
    c = P.mean(0)
    _, _, vt = np.linalg.svd(P - c, full_matrices=False)
    n = vt[-1]
    if np.dot(n, best[0]) < 0:
        n = -n
    d = -float(np.dot(n, c))
    inl = np.abs(pts @ n + d) < inlier_dist
    return n, d, inl


class FloorTracker:
    """Suit le plan du sol dans le repère VO (première caméra) et fournit l'alignement z-haut."""

    def __init__(self, cfg_floor, seed: int = 0) -> None:
        c = cfg_floor
        self.bottom = float(c.bottom_fraction)
        self.iters = int(c.ransac_iters)
        self.inlier_dist = float(c.inlier_dist_m)
        self.min_inliers = int(c.min_inliers)
        self.alpha = float(c.update_alpha)
        self.max_tilt = float(c.max_tilt_deg)
        self.step = int(c.pixel_step)
        self.rng = np.random.default_rng(seed)
        self.n: np.ndarray | None = None  # normale (vers le haut) en repère VO
        self.d = 0.0
        self.n_updates = 0
        self.heading_ref: np.ndarray | None = None  # axe avant de la première caméra (repère VO)
        self.origin_ref: np.ndarray | None = None

    @property
    def ready(self) -> bool:
        return self.n is not None

    def update(self, depth: np.ndarray, K: np.ndarray, T_vo_cam: np.ndarray) -> bool:
        """Met à jour le plan à partir de la moitié basse de l'image. Retourne True si mesuré."""
        h = depth.shape[0]
        mask = np.zeros(depth.shape, bool)
        mask[int(h * (1 - self.bottom)) :] = True
        pc, _ = backproject(depth, K, self.step, mask, 0.2, 6.0)
        if len(pc) < self.min_inliers:
            return False
        pw = transform(T_vo_cam, pc)
        # indice « haut » : −y caméra (image droite) ou normale courante
        up_hint = self.n if self.n is not None else -T_vo_cam[:3, 1]
        cam = T_vo_cam[:3, 3]
        res = fit_plane_ransac(pw, self.iters, self.inlier_dist, self.rng, up_hint, self.max_tilt)
        if res is None:
            return False
        n, d, inl = res
        if inl.sum() < self.min_inliers or np.dot(n, cam) + d < 0.3:
            return False  # pas assez de sol, ou caméra sous le « sol » (mur, meuble)
        if self.n is None:
            self.n, self.d = n, d
            self.heading_ref = T_vo_cam[:3, 2].copy()
            self.origin_ref = cam.copy()
        else:
            if (
                np.degrees(np.arccos(np.clip(np.dot(n, self.n), -1, 1))) > 10
                or abs((np.dot(n, cam) + d) - self.height(cam)) > 0.3
            ):
                return False  # mesure aberrante (table, lit…) : rejetée
            a = self.alpha
            nn = (1 - a) * self.n + a * n
            self.n = nn / np.linalg.norm(nn)
            self.d = (1 - a) * self.d + a * d
        self.n_updates += 1
        return True

    def height(self, p_vo: np.ndarray) -> float:
        """Hauteur d'un point (repère VO) au-dessus du sol."""
        return float(np.dot(self.n, p_vo) + self.d)

    def T_world_vo(self) -> np.ndarray:
        """Repère monde : z = normale du sol, x = cap initial projeté, origine au sol sous la 1re caméra."""
        z = self.n
        f = self.heading_ref - np.dot(self.heading_ref, z) * z
        if np.linalg.norm(f) < 1e-6:
            f = np.cross(z, [1.0, 0, 0])
        x = f / np.linalg.norm(f)
        y = np.cross(z, x)
        R = np.stack([x, y, z])  # lignes : axes monde exprimés en VO
        o = self.origin_ref - self.height(self.origin_ref) * z  # pied de la première caméra
        return make_T(R, -R @ o)
