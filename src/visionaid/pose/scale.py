"""Recalage d'échelle de la profondeur monoculaire par la hauteur de caméra déclarée.

Avec la direction « haut » en repère caméra (gravité), la distance caméra → sol se mesure sur les
points bas de l'image. Le facteur s = hauteur déclarée / hauteur mesurée est lissé (en log) et
borné, puis appliqué à la profondeur. Remplace le facteur fixe calibré sur une seule vidéo.
"""

from __future__ import annotations

import math

import numpy as np

from visionaid.bus.messages import Depth
from visionaid.mapping.geometry import backproject


class DepthScaleCorrector:
    """Facteur d'échelle multiplicatif de la profondeur, ré-estimé en continu."""

    def __init__(
        self,
        camera_height_m: float,
        ema: float = 0.1,
        bounds: tuple[float, float] = (0.5, 2.0),
        min_points: int = 150,
        bin_m: float = 0.02,
        bottom_fraction: float = 0.5,
        pixel_step: int = 6,
        min_height_m: float = 0.5,
        n_init: int = 5,
        max_jump: float = 1.3,
    ) -> None:
        self.h_ref = float(camera_height_m)
        self.ema = float(ema)
        self.lo, self.hi = bounds
        self.min_points = int(min_points)
        self.bin = float(bin_m)
        self.bottom = float(bottom_fraction)
        self.step = int(pixel_step)
        self.min_h = float(min_height_m)
        self.log_s = 0.0
        self.n_updates = 0
        self.n_rejected = 0
        self.n_init = int(n_init)
        self.max_jump = float(max_jump)
        self._init: list[float] = []
        self.history: list[float] = []

    @property
    def scale(self) -> float:
        return math.exp(self.log_s)

    def measure_height(self, depth: np.ndarray, K: np.ndarray, up_cam: np.ndarray) -> float | None:
        """Hauteur caméra → sol mesurée sur la profondeur brute (sans correction)."""
        h = depth.shape[0]
        mask = np.zeros(depth.shape, bool)
        mask[int(h * (1 - self.bottom)) :] = True
        pc, _ = backproject(depth, K, self.step, mask, 0.2, 8.0)
        if len(pc) < self.min_points:
            return None
        below = -(
            pc @ (np.asarray(up_cam, float) / np.linalg.norm(up_cam))
        )  # distance sous la caméra
        below = below[below > 0.5 * self.min_h / self.scale]  # seuil exprimé en profondeur brute
        if len(below) < self.min_points:
            return None
        # le sol est la surface la plus basse : le mode le plus bas parmi les modes denses
        edges = np.arange(below.min(), below.max() + 2 * self.bin, self.bin)  # ≥ 2 bords
        if len(edges) < 2:
            return None
        hist, edges = np.histogram(below, edges)
        hs = hist + np.r_[hist[1:], 0] + np.r_[0, hist[:-1]]  # lissage sur 3 bins
        # seuil ABSOLU (et non relatif au mode principal) : quand la caméra vise une table, le
        # dessus de table domine et le sol, plus bas, n'est qu'un mode secondaire (essai réel)
        need = max(self.min_points / 3.0, 0.04 * len(below))
        dense = np.nonzero((hs >= need) & (hist > 0))[0]
        if len(dense) == 0:
            return None
        k = int(dense.max())
        lo, hi = edges[max(k - 1, 0)], edges[min(k + 2, len(edges) - 1)]
        sel = below[(below >= lo) & (below <= hi)]
        if len(sel) < self.min_points // 3:
            return None
        return float(np.median(sel))

    def update(self, depth: np.ndarray, K: np.ndarray, up_cam: np.ndarray | None) -> float:
        """Met à jour le facteur à partir d'une profondeur brute ; renvoie le facteur courant."""
        if up_cam is None:
            return self.scale
        h = self.measure_height(depth, K, up_cam)
        if h is None or h <= 0:
            return self.scale
        s_meas = float(np.clip(self.h_ref / h, self.lo, self.hi))
        if self.n_updates == 0:  # démarrage robuste : médiane des premières mesures
            self._init.append(s_meas)
            if len(self._init) < self.n_init:
                return self.scale
            s_meas = float(np.median(self._init))
            a = 1.0
        else:
            if abs(math.log(s_meas) - self.log_s) > math.log(self.max_jump):
                self.n_rejected += 1  # saut d'échelle invraisemblable : autre surface que le sol
                return self.scale
            a = self.ema
        self.log_s = (1 - a) * self.log_s + a * math.log(s_meas)
        self.log_s = float(np.clip(self.log_s, math.log(self.lo), math.log(self.hi)))
        self.n_updates += 1
        self.history.append(self.scale)
        return self.scale

    def __call__(self, depth: Depth, K: np.ndarray, up_cam: np.ndarray | None) -> Depth:
        """Profondeur corrigée (nouvel objet ; l'entrée n'est pas modifiée)."""
        s = self.update(depth.depth, K, up_cam)
        return Depth(
            depth.t, depth.frame_idx, (depth.depth * s).astype(np.float32), depth.confidence
        )
