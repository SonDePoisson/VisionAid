"""Suivi multi-objets (IoU + vitesse constante, affectation hongroise) et décision « cible » par piste."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

from visionaid.bus.messages import Detections


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU entre boîtes xyxy (N,4) et (M,4)."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    x0 = np.maximum(a[:, None, 0], b[None, :, 0])
    y0 = np.maximum(a[:, None, 1], b[None, :, 1])
    x1 = np.minimum(a[:, None, 2], b[None, :, 2])
    y1 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x1 - x0, 0, None) * np.clip(y1 - y0, 0, None)
    aa = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    ab = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / np.maximum(aa[:, None] + ab[None, :] - inter, 1e-9)


def center_dist(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Distance entre centres normalisée par la diagonale de la boîte de piste."""
    ca = np.stack([(a[:, 0] + a[:, 2]) / 2, (a[:, 1] + a[:, 3]) / 2], 1)
    cb = np.stack([(b[:, 0] + b[:, 2]) / 2, (b[:, 1] + b[:, 3]) / 2], 1)
    diag = np.hypot(a[:, 2] - a[:, 0], a[:, 3] - a[:, 1])
    return np.linalg.norm(ca[:, None] - cb[None], axis=2) / np.maximum(diag[:, None], 1e-6)


@dataclass
class Track:
    """Piste d'un objet."""

    id: int
    box: np.ndarray
    vel: np.ndarray = field(default_factory=lambda: np.zeros(4))
    hits: int = 1
    misses: int = 0
    score_ema: float = 0.0
    above: int = 0  # frames consécutives au-dessus du seuil
    below: int = 0  # frames consécutives sous le seuil bas (une fois confirmée)
    confirmed: bool = False
    label: str = ""

    def predict(self) -> np.ndarray:
        return self.box + self.vel


class TargetTracker:
    """Pistes + hystérésis : confirmée après N frames ≥ seuil, perdue après M frames sans détection."""

    def __init__(self, cfg, threshold: float) -> None:
        t = cfg.tracker
        self.iou_match = float(t.iou_match)
        self.confirm_frames = int(t.confirm_frames)
        self.lost_frames = int(t.lost_frames)
        self.max_age = int(t.max_age_frames)
        self.alpha = float(t.score_ema)
        self.threshold = float(threshold)
        self.low_threshold = 0.85 * self.threshold
        self.reject_threshold = 0.6 * self.threshold
        self.tracks: list[Track] = []
        self._next_id = 1
        self.target_id = -1

    def _match(self, boxes: np.ndarray, scores: np.ndarray) -> list[tuple[int, int]]:
        if not self.tracks or len(boxes) == 0:
            return []
        pred = np.stack([t.predict() for t in self.tracks])
        iou = iou_matrix(pred, boxes)
        cd = center_dist(pred, boxes)
        cost = 1.0 - iou + 0.5 * np.minimum(cd, 2.0)
        gate = (iou >= self.iou_match) | (cd < 0.5)
        # Gating d'apparence : une piste confirmée ne peut pas absorber un objet d'apparence
        # incompatible (sinon elle « saute » sur un voisin quand la cible n'est pas détectée).
        conf = np.array([t.confirmed for t in self.tracks])
        incompatible = scores[None, :] < self.reject_threshold
        gate &= ~(conf[:, None] & incompatible)
        cost[~gate] = 1e6
        r, c = linear_sum_assignment(cost)
        return [(i, j) for i, j in zip(r, c, strict=True) if gate[i, j]]

    def update(self, dets: Detections, reid_scores: np.ndarray | None) -> Detections:
        """Met à jour les pistes ; remplit `track_ids`, `reid_scores`, `target_idx`, `target_track_id`."""
        n = len(dets.boxes)
        scores = (
            np.zeros(n, np.float32) if reid_scores is None else np.asarray(reid_scores, np.float32)
        )
        matches = self._match(dets.boxes, scores)
        matched_t = {i for i, _ in matches}
        matched_d = {j for _, j in matches}
        track_ids = np.full(n, -1, int)
        for i, j in matches:
            tr = self.tracks[i]
            new = dets.boxes[j].astype(np.float64)
            tr.vel = 0.5 * tr.vel + 0.5 * (new - tr.box) / (tr.misses + 1)
            tr.box = new
            tr.hits += 1
            tr.misses = 0
            tr.label = dets.labels[j] if j < len(dets.labels) else tr.label
            self._update_score(tr, float(scores[j]))
            track_ids[j] = tr.id
        for i, tr in enumerate(self.tracks):
            if i not in matched_t:
                tr.misses += 1
                tr.box = tr.predict()
                tr.vel *= 0.5
                tr.above = 0
                if tr.misses >= self.lost_frames:
                    tr.confirmed = False
        for j in range(n):
            if j not in matched_d:
                tr = Track(
                    id=self._next_id,
                    box=dets.boxes[j].astype(np.float64),
                    label=dets.labels[j] if j < len(dets.labels) else "",
                )
                self._next_id += 1
                tr.score_ema = float(scores[j])
                self._update_score(tr, float(scores[j]), init=True)
                self.tracks.append(tr)
                track_ids[j] = tr.id
        self.tracks = [t for t in self.tracks if t.misses <= self.max_age]
        self._select_target()
        target_idx = -1
        if self.target_id >= 0:
            hits = np.where(track_ids == self.target_id)[0]
            # la détection n'est attribuée à la cible que si son apparence reste plausible
            if len(hits) and scores[hits[0]] >= self.low_threshold:
                target_idx = int(hits[0])
        dets.track_ids = track_ids
        dets.reid_scores = scores
        dets.target_idx = target_idx
        dets.target_track_id = self.target_id
        return dets

    def _update_score(self, tr: Track, s: float, init: bool = False) -> None:
        if not init:
            tr.score_ema = self.alpha * s + (1 - self.alpha) * tr.score_ema
        if s >= self.threshold:
            tr.above += 1
            tr.below = 0
        else:
            tr.above = 0
            tr.below = tr.below + 1 if s < self.low_threshold else 0
        if not tr.confirmed and tr.above >= self.confirm_frames:
            tr.confirmed = True
        if tr.confirmed and tr.below >= self.lost_frames:
            tr.confirmed = False

    def _select_target(self) -> None:
        conf = [t for t in self.tracks if t.confirmed]
        if not conf:
            self.target_id = -1
            return
        current = [t for t in conf if t.id == self.target_id]
        if current:
            return
        self.target_id = max(conf, key=lambda t: t.score_ema).id

    @property
    def target_track(self) -> Track | None:
        for t in self.tracks:
            if t.id == self.target_id:
                return t
        return None
