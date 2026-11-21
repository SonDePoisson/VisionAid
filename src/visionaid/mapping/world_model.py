"""Modèle du monde : sol + costmap + ancrage de la cible, à partir de (frame, profondeur, pose, détections)."""

from __future__ import annotations

from typing import Any

import numpy as np

from visionaid.bus.messages import Costmap, Depth, Detections, Frame, ObjectEstimate, Pose
from visionaid.mapping.costmap import OccupancyGrid
from visionaid.mapping.floor import FloorTracker
from visionaid.mapping.geometry import backproject, transform
from visionaid.mapping.object_anchor import ObjectAnchor


class WorldModel:
    """Fusion 3D. Les poses VO sont réexprimées dans le repère monde aligné (z haut, sol z=0)."""

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.floor = FloorTracker(cfg.floor)
        self.grid = OccupancyGrid(cfg.costmap)
        self.anchor = ObjectAnchor(cfg.anchor)
        self.step = int(cfg.costmap.pixel_step)
        self.cam_heights: list[float] = []
        self.T_world_cam: np.ndarray | None = None
        self.pose_quality = "init"
        self._pending: list[tuple] = []  # mesures de cible reçues avant l'alignement du sol
        self._t_prev: float | None = None

    def T_aligned(self, T_vo_cam: np.ndarray) -> np.ndarray:
        return self.floor.T_world_vo() @ T_vo_cam

    def update(
        self, frame: Frame, depth: Depth, pose: Pose, dets: Detections | None
    ) -> tuple[Costmap | None, ObjectEstimate]:
        t = frame.t
        self.pose_quality = pose.quality
        lost = pose.quality == "lost"
        if not lost:
            self.floor.update(depth.depth, frame.K, pose.T_world_cam)
        target = None
        if dets is not None and dets.target_idx >= 0:
            i = dets.target_idx
            mask = None
            if dets.masks is not None:
                from visionaid.perception.pipeline import unpack_masks

                mask = unpack_masks(dets, frame.image.shape[1])[i]
            conf = float(dets.reid_scores[i]) if dets.reid_scores is not None else 1.0
            target = (mask, dets.boxes[i], conf)
        if not self.floor.ready:
            if target is not None and not lost:
                self._pending.append((t, pose.T_world_cam.copy(), depth.depth, frame.K, *target))
            self.anchor.predict(t)
            return None, self.anchor.estimate(t, frame.frame_idx)
        if self._pending:
            for tp, Tp, dp, Kp, m, b, c in self._pending:
                self.anchor.update(tp, self.T_aligned(Tp), dp, Kp, m, b, c)
            self._pending = []
        T = self.T_aligned(pose.T_world_cam)
        self.T_world_cam = T
        self.cam_heights.append(float(T[2, 3]))
        if not lost:
            pc, _ = backproject(
                depth.depth, frame.K, self.step, None, 0.2, float(self.cfg.costmap.max_range_m) + 1
            )
            dt = 1.0 / 30.0 if self._t_prev is None else max(t - self._t_prev, 0.0)
            self.grid.update(transform(T, pc), T[:3, 3], dt)
            self._t_prev = t
            if target is not None:
                m, b, c = target
                self.anchor.update(t, T, depth.depth, frame.K, m, b, c)
            else:
                self.anchor.predict(t)
        else:
            self.anchor.predict(t)
        return self.grid.to_msg(t, frame.frame_idx), self.anchor.estimate(t, frame.frame_idx)

    # interface Block du bus
    def process(self, inputs: dict[str, Any]) -> dict[str, Any] | None:
        f, d, p = inputs.get("frame"), inputs.get("depth"), inputs.get("pose")
        if f is None or d is None or p is None or not (f.frame_idx == d.frame_idx == p.frame_idx):
            return None
        dets = inputs.get("detections")
        if dets is not None and dets.frame_idx != f.frame_idx:
            dets = None
        cm, obj = self.update(f, d, p, dets)
        out: dict[str, Any] = {"object": obj}
        if cm is not None:
            out["costmap"] = cm
            out["pose_world"] = Pose(
                p.t,
                p.frame_idx,
                self.T_world_cam,
                p.quality,
                p.n_inliers,
                p.reproj_err,
                p.is_keyframe,
            )
        return out


def run_mapping_video(cfg, dets_by_idx: dict | None = None):
    """Profondeur (cache) + VO + modèle du monde sur toute la vidéo. Retourne (world, records)."""
    from visionaid.io.sources import VideoFileSource
    from visionaid.perception.depth import video_depth_estimator
    from visionaid.pose.source import VisualOdometry

    src = VideoFileSource.from_config(cfg)
    dest = video_depth_estimator(cfg)
    vo = VisualOdometry(cfg)
    wm = WorldModel(cfg)
    records = []
    while (f := src.read()) is not None:
        d = dest(f)
        p = vo.update(f, d)
        det = (dets_by_idx or {}).get(f.frame_idx)
        cm, obj = wm.update(f, d, p, det)
        records.append(
            {
                "frame_idx": f.frame_idx,
                "t": f.t,
                "pose_quality": p.quality,
                "T_world_cam": None if wm.T_world_cam is None else wm.T_world_cam.copy(),
                "object": obj,
                "target_seen": det is not None and det.target_idx >= 0,
            }
        )
    return wm, records
