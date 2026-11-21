"""Bloc perception (détection + ReID + suivi), commun aux modes offline et temps réel."""

from __future__ import annotations

import json
import pickle
import time
from typing import Any

import numpy as np

from visionaid.bus.messages import Detections, Frame
from visionaid.utils.config import load_config, resolve_path, to_dict
from visionaid.utils.logging import get_logger
from visionaid.utils.report import file_hash

log = get_logger("perception")


class PerceptionBlock:
    """Image → Detections avec décision « cible » (piste confirmée)."""

    def __init__(self, cfg, detector=None, reid=None) -> None:
        from visionaid.perception.tracker import TargetTracker

        self.cfg = cfg
        if detector is None or reid is None:
            from visionaid.apps.calibrate_reid import build_reid

            reid, _rc, detector = build_reid(cfg, detector)
        self.detector = detector
        self.reid = reid
        self.tracker = TargetTracker(cfg, reid.threshold)
        self.times: list[float] = []

    def __call__(self, frame: Frame) -> Detections:
        t0 = time.perf_counter()
        d = self.detector.detect(frame.image, frame.t, frame.frame_idx)
        scores = (
            self.reid.score_detections(frame.image, d.boxes, d.masks)
            if len(d.boxes)
            else np.zeros(0, np.float32)
        )
        d = self.tracker.update(d, scores)
        self.times.append(time.perf_counter() - t0)
        return d

    # interface Block du bus
    def process(self, inputs: dict[str, Any]) -> dict[str, Any] | None:
        f = inputs.get("frame")
        if f is None:
            return None
        return {"detections": self(f)}


def make_perception_block(cfg_raw: dict) -> PerceptionBlock:
    from visionaid.utils.config import _to_dataclass

    return PerceptionBlock(_to_dataclass("config", cfg_raw))


def run_video_perception(
    cfg=None, video=None, use_cache: bool = True
) -> tuple[list[Detections], dict]:
    """Perception sur toute la vidéo, avec cache disque (.cache/perception/<hash>.pkl)."""
    from visionaid.io.sources import VideoFileSource

    cfg = cfg or load_config()
    video = resolve_path(video or cfg.paths.video)
    key_cfg = json.dumps(
        {
            k: to_dict(getattr(cfg, k))
            for k in ("detector", "reid", "tracker", "video", "intrinsics")
        },
        sort_keys=True,
    )
    th_file = resolve_path(cfg.reid.threshold_file)
    key_cfg += th_file.read_text() if th_file.exists() else ""
    key = file_hash(video, key_cfg)
    cpath = resolve_path(cfg.paths.cache) / "perception" / f"{video.stem}_{key}.pkl"
    if use_cache and cpath.exists():
        data = pickle.loads(cpath.read_bytes())
        return data["dets"], data["info"]
    block = PerceptionBlock(cfg)
    src = VideoFileSource.from_config(cfg, path=video)
    dets = []
    while (f := src.read()) is not None:
        d = block(f)
        if d.masks is not None:  # compression des masques (packbits sur la largeur)
            d.masks = np.packbits(d.masks, axis=-1)
        dets.append(d)
    times = np.asarray(block.times[5:] or block.times)
    info = {
        "detector_backend": block.detector.backend,
        "detector_weights": block.detector.weights,
        "reid_backend": block.reid.backend,
        "threshold": block.reid.threshold,
        "n_frames": len(dets),
        "perception_fps": float(1.0 / times.mean()) if len(times) else 0.0,
        "perception_ms_p50": float(np.median(times) * 1e3) if len(times) else 0.0,
        "image_shape": [src.out_h, src.out_w],
        "device": block.detector.device,
    }
    cpath.parent.mkdir(parents=True, exist_ok=True)
    cpath.write_bytes(pickle.dumps({"dets": dets, "info": info}))
    return dets, info


def unpack_masks(d: Detections, width: int) -> np.ndarray | None:
    """Décompresse les masques stockés en cache (packbits)."""
    if d.masks is None:
        return None
    if d.masks.dtype == bool:
        return d.masks
    return np.unpackbits(d.masks, axis=-1, count=width).astype(bool)
