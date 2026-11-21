"""Sources de pose : odométrie visuelle (implémentée) et ARKit (stub)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np

from visionaid.bus.messages import Depth, Frame, Pose
from visionaid.pose.vo import RGBDOdometry


@runtime_checkable
class PoseSource(Protocol):
    """Contrat : (frame, profondeur) → Pose horodatée (T_world_cam, qualité)."""

    def update(self, frame: Frame, depth: Depth | None) -> Pose: ...


class VisualOdometry:
    """PoseSource par odométrie RGB-D (profondeur métrique monoculaire comme canal D)."""

    def __init__(self, cfg) -> None:
        self.vo = RGBDOdometry(cfg.vo)

    def update(self, frame: Frame, depth: Depth | None) -> Pose:
        d = depth.depth if depth is not None else np.zeros(frame.image.shape[:2], np.float32)
        obs = self.vo.observe(frame.image, d)
        return self.vo.step(obs, frame.K, frame.t, frame.frame_idx)

    @property
    def lost_fraction(self) -> float:
        return self.vo.n_lost / max(self.vo.n_frames, 1)

    # interface Block du bus
    def process(self, inputs: dict[str, Any]) -> dict[str, Any] | None:
        f, d = inputs.get("frame"), inputs.get("depth")
        if f is None or d is None or d.frame_idx != f.frame_idx:
            return None
        return {"pose": self.update(f, d)}


class ArkitPoseSource:
    """Stub : pose 6DoF fournie par ARKit sur le téléphone (à venir).

    Contrat attendu : pour chaque frame, `T_world_cam` exprimée dans le repère monde ARKit
    (y vers le haut chez ARKit → à convertir vers z vers le haut, voir docs/frames.md),
    horodatée avec la même horloge que les images (`t`), `quality` dérivée de
    `ARCamera.trackingState` (normal → ok, limited → ok avec n_inliers=0, notAvailable → lost).
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError("ArkitPoseSource n'est pas encore implémentée")

    def update(self, frame: Frame, depth: Depth | None) -> Pose:  # pragma: no cover
        raise NotImplementedError


def run_vo_video(cfg, frames=None, depth_est=None) -> tuple[list[Pose], VisualOdometry]:
    """Odométrie sur une séquence de frames (par défaut toute la vidéo), profondeur en cache."""
    from visionaid.io.sources import VideoFileSource
    from visionaid.perception.depth import video_depth_estimator

    depth_est = depth_est or video_depth_estimator(cfg)
    if frames is None:
        frames = VideoFileSource.from_config(cfg)
    vo = VisualOdometry(cfg)
    poses = [vo.update(f, depth_est(f)) for f in frames]
    return poses, vo
