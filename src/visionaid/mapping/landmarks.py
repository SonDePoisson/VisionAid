"""Carte des meubles (tables, canapé, chaises…) : de quoi dire « la gourde est sur la table ».

Chaque meuble détecté (masque YOLOE + profondeur) est remonté en 3D dans le repère monde aligné
(z haut, sol à z = 0). On en garde l'emprise au sol (rectangle x, y) et la hauteur du dessus.
Les observations successives d'un même meuble sont fusionnées : même famille de meuble (ou
emprises qui se recouvrent) et centres proches.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from visionaid.bus.messages import Landmarks

# familles : une table vue comme « desk » puis « table » reste le même meuble
GROUPS = {
    "table": "table",
    "coffee table": "table",
    "desk": "table",
    "kitchen counter": "table",
    "sofa": "seat",
    "armchair": "seat",
    "chair": "chair",
    "bed": "bed",
    "shelf": "storage",
    "cabinet": "storage",
    "door": "door",
    "television": "tv",
}


@dataclass
class Landmark:
    box: np.ndarray  # xmin, ymin, xmax, ymax
    top_z: float
    votes: dict = field(default_factory=dict)  # label -> somme des confiances
    n_obs: int = 1
    t_last: float = 0.0

    @property
    def label(self) -> str:
        return max(self.votes, key=self.votes.get)

    @property
    def center(self) -> np.ndarray:
        return np.array([(self.box[0] + self.box[2]) / 2, (self.box[1] + self.box[3]) / 2])


def box_overlap(a: np.ndarray, b: np.ndarray) -> float:
    """Recouvrement des emprises, rapporté à la plus petite (0 à 1)."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    area = lambda r: max((r[2] - r[0]) * (r[3] - r[1]), 1e-6)  # noqa: E731
    return float(w * h / min(area(a), area(b)))


class LandmarkMap:
    """Meubles repérés, mis à jour à chaque détection de meubles."""

    def __init__(self, cfg_landmarks) -> None:
        c = cfg_landmarks
        self.step = int(getattr(c, "pixel_step", 4))
        self.max_range = float(getattr(c, "max_range_m", 4.5))
        self.min_points = int(getattr(c, "min_points", 40))
        self.merge_m = float(getattr(c, "merge_m", 0.6))
        self.ema = float(getattr(c, "ema", 0.3))
        self.min_obs = int(getattr(c, "min_obs", 3))
        self.max_count = int(getattr(c, "max_count", 40))
        self.items: list[Landmark] = []
        self.n_updates = 0

    def observe(self, label: str, score: float, pts_world: np.ndarray, t: float) -> None:
        """Ajoute une observation (points 3D monde du meuble)."""
        p = pts_world[(pts_world[:, 2] > 0.05) & (pts_world[:, 2] < 2.2)]
        if len(p) < self.min_points:
            return
        lo = np.percentile(p[:, :2], 5, axis=0)
        hi = np.percentile(p[:, :2], 95, axis=0)
        box = np.array([lo[0], lo[1], hi[0], hi[1]])
        top = float(np.percentile(p[:, 2], 95))
        grp = GROUPS.get(label, label)
        best, best_d = None, np.inf
        c = (box[:2] + box[2:]) / 2
        for lm in self.items:
            same = GROUPS.get(lm.label, lm.label) == grp
            d = float(np.linalg.norm(lm.center - c))
            ov = box_overlap(lm.box, box)
            if (same and (d < self.merge_m or ov > 0.3)) or ov > 0.6:
                if d < best_d:
                    best, best_d = lm, d
        if best is None:
            self.items.append(Landmark(box, top, {label: float(score)}, 1, t))
            if len(self.items) > self.max_count:  # oubli du meuble le moins vu
                self.items.remove(min(self.items, key=lambda m: (m.n_obs, m.t_last)))
        else:
            a = self.ema
            # l'emprise grandit vite (vues partielles successives), rétrécit lentement
            grow = np.r_[np.minimum(best.box[:2], box[:2]), np.maximum(best.box[2:], box[2:])]
            best.box = (1 - a) * best.box + a * (0.5 * grow + 0.5 * box)
            best.top_z = (1 - a) * best.top_z + a * top
            best.votes[label] = best.votes.get(label, 0.0) + float(score)
            best.n_obs += 1
            best.t_last = t
        self.n_updates += 1

    def update(self, t: float, T_world_cam, depth: np.ndarray, K: np.ndarray, dets, masks) -> None:
        """Meubles d'une image (masques déjà décompressés)."""
        from visionaid.mapping.geometry import backproject, transform

        if dets is None or not len(dets.boxes):
            return
        import cv2

        h, w = depth.shape
        for i in range(len(dets.boxes)):
            if masks is not None and i < len(masks):
                m = masks[i]
                if m.shape != (h, w):
                    m = cv2.resize(m.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST) > 0
            else:
                x0, y0, x1, y1 = np.clip(dets.boxes[i], 0, [w, h, w, h]).astype(int)
                m = np.zeros((h, w), bool)
                m[y0:y1, x0:x1] = True
            # bords du masque érodés : la profondeur y saute souvent sur le fond (mur, sol)
            m = cv2.erode(m.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
            pc, _ = backproject(depth, K, self.step, m, 0.2, self.max_range)
            if len(pc) < self.min_points:
                continue
            lab = dets.labels[i] if i < len(dets.labels) else "meuble"
            self.observe(lab, float(dets.scores[i]), transform(T_world_cam, pc), t)

    def confirmed(self) -> list[Landmark]:
        return [m for m in self.items if m.n_obs >= self.min_obs]

    def to_msg(self, t: float) -> Landmarks:
        ms = self.confirmed()
        return Landmarks(
            t=float(t),
            labels=[m.label for m in ms],
            centers=np.array([m.center for m in ms], float).reshape(-1, 2),
            boxes=np.array([m.box for m in ms], float).reshape(-1, 4),
            top_z=np.array([m.top_z for m in ms], float),
            n_obs=np.array([m.n_obs for m in ms], int),
        )
