"""Blocs du graphe « téléphone → chemin » (phase 20), importables par les sous-processus du bus."""

from __future__ import annotations

import json
import math
import time
from typing import Any

import numpy as np

from visionaid.bus.messages import Path
from visionaid.utils.config import _to_dataclass, resolve_path


def _cfg(raw: dict):
    return _to_dataclass("config", raw)


# ---------------------------------------------------------------------------- source
def make_phone_source(raw: dict):
    """Serveur téléphone (direct ou faux téléphone piloté par le processus principal)."""
    from visionaid.phone.block import PhoneSourceBlock

    return PhoneSourceBlock(raw)


# ---------------------------------------------------------------------------- modèles (ou stubs)
STUB_BOX = np.array([150, 300, 175, 360], float)


def stub_scene_depth(h: int, w: int, K: np.ndarray, pitch_deg: float = 20.0, cam_h: float = 1.4):
    """Profondeur d'un sol vu par une caméra inclinée, mur à 5 m (tests sans modèle)."""
    v, _u = np.mgrid[0:h, 0:w]
    y = (v - K[1, 2]) / K[1, 1]
    p = math.radians(pitch_deg)
    den = math.cos(p) * y + math.sin(p)
    floor = np.where(den > 1e-3, cam_h / np.maximum(den, 1e-3), np.inf)
    return np.minimum(floor, 5.0).astype(np.float32)


def make_live_perception(raw: dict):
    """Perception réelle, ou stub (boîte fixe, ReID texte seul) si `_stub_models`."""
    cfg = _cfg(raw)
    from visionaid.perception.pipeline import PerceptionBlock

    if not raw.get("_stub_models"):
        return PerceptionBlock(cfg)
    from visionaid.perception.detector import StubDetector
    from visionaid.perception.reid import TextOnlyReID

    det = StubDetector(fn=lambda img, k: [(STUB_BOX, 0.9, "bottle")])
    det.backend, det.weights, det.device = "stub", "stub", "cpu"
    return PerceptionBlock(cfg, detector=det, reid=TextOnlyReID(cfg))


class LiveGeometryBlock:
    """Profondeur + pose (VIO si IMU) ; intrinsèques de l'appareil ; profondeur stub si demandé."""

    def __init__(self, raw: dict) -> None:
        from visionaid.perception.depth import DepthEstimator, StubDepthBackend
        from visionaid.pose.source import make_pose_source

        cfg = _cfg(raw)
        if raw.get("_stub_models"):
            self.depth = DepthEstimator(
                cfg,
                backend=StubDepthBackend(lambda h, w: stub_scene_depth(h, w, self._K(h, w))),
            )
        else:
            self.depth = DepthEstimator(cfg)
        self.cfg = cfg
        self.vo = make_pose_source(cfg, bool(raw.get("_imu", True)))
        self._Kc: dict = {}
        self.n = 0
        self.t_proc: list[float] = []

    def _K(self, h: int, w: int) -> np.ndarray:
        from visionaid.calib.device import phone_intrinsics

        if (w, h) not in self._Kc:
            self._Kc[(w, h)] = phone_intrinsics(self.cfg, w, h).K
        return self._Kc[(w, h)]

    def process(self, inputs: dict[str, Any]) -> dict[str, Any] | None:
        from visionaid.pose.source import merge_imu

        if hasattr(self.vo, "add_imu"):
            self.vo.add_imu(merge_imu(inputs.get("imu")))
        f = inputs.get("frame")
        if f is None:
            return None
        t0 = time.perf_counter()
        d = self.depth(f)
        if hasattr(self.vo, "correct_depth"):
            d = self.vo.correct_depth(f, d)
        p = self.vo.update(f, d)
        self.t_proc.append(time.perf_counter() - t0)
        self.n += 1
        return {"depth": d, "pose": p}

    def stats(self) -> dict:
        s = {"n": self.n}
        if self.t_proc:
            s["process_ms_p50"] = float(np.percentile(self.t_proc, 50) * 1e3)
        if hasattr(self.vo, "stats"):
            s.update(self.vo.stats())
        else:
            s["lost_fraction"] = self.vo.lost_fraction
        return s


def make_live_world(raw: dict):
    """Modèle du monde avec les intrinsèques de l'appareil (calibration de la phase 17)."""
    from visionaid.apps.realtime_blocks import WorldBlock

    blk = WorldBlock(raw)
    blk.use_phone_intrinsics = True
    return blk


# ---------------------------------------------------------------------------- planification
class LivePlannerBlock:
    """Planificateur à cadence fixe avec chien de garde.

    Replanifie sur une costmap nouvelle ; si aucune pose fraîche n'est arrivée depuis `stale_s`
    (téléphone déconnecté, pose perdue), publie un chemin **invalide** (une fois par seconde).
    """

    def __init__(self, raw: dict, stale_s: float = 1.5) -> None:
        from visionaid.planning.planner import Planner

        self.planner = Planner(_cfg(raw))
        self.stale_s = stale_s
        self._last_pose_key = None
        self._last_pose_wall = time.time()
        self._last_cm_key = None
        self._last_invalid = 0.0
        self.n_plans = 0
        self.n_invalid_stale = 0

    def process(self, inputs: dict[str, Any]) -> dict[str, Any] | None:
        now = time.time()
        pose = inputs.get("pose_world")
        if pose is not None:
            key = (pose.frame_idx, pose.t)
            if key != self._last_pose_key:
                self._last_pose_key = key
                self._last_pose_wall = now
        stale = now - self._last_pose_wall > self.stale_s or (
            pose is not None and pose.quality == "lost"
        )
        if stale:
            if now - self._last_invalid >= 1.0:
                self._last_invalid = now
                self.n_invalid_stale += 1
                t = pose.t if pose is not None else 0.0
                idx = pose.frame_idx if pose is not None else -1
                nan2 = np.full(2, np.nan)
                return {"path": Path(t, idx, np.zeros((0, 2)), nan2, nan2, False, 0.0)}
            return None
        cm, obj = inputs.get("costmap"), inputs.get("object")
        if cm is None or obj is None or pose is None:
            return None
        ck = (cm.frame_idx, cm.t)
        if ck == self._last_cm_key:
            return None
        self._last_cm_key = ck
        self.n_plans += 1
        return {"path": self.planner.plan(cm, pose.T_world_cam[:2, 3], obj)}

    def stats(self) -> dict:
        return {"n_plans": self.n_plans, "n_invalid_stale": self.n_invalid_stale}


# ---------------------------------------------------------------------------- puits
class PathSink:
    """Mesure : latence capture → chemin publié, cadence de chemins valides, état de la cible.

    Temps de capture côté PC : `t_phone + offset` (horloge synchronisée, sujet `clock`) en direct ;
    `_t0_wall + t` en rejeu de session (temps ramené au début, comme le temps vidéo).
    """

    def __init__(self, raw: dict) -> None:
        self.t0_wall = raw.get("_t0_wall")
        self.offset: float | None = None
        self.lat: list[float] = []
        self.valid_times: list[float] = []
        self.invalid_times: list[float] = []
        self.first_valid_wall: float | None = None
        self.t_start = time.time()
        self.obj_states: dict[str, int] = {}
        self.out = resolve_path(raw["paths"]["outputs"]) / "live_paths.jsonl"
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.out, "w")  # noqa: SIM115
        self.live = bool(raw.get("_live_clock", True))

    def process(self, inputs: dict[str, Any]) -> dict[str, Any] | None:
        c = inputs.get("clock")
        if c is not None and math.isfinite(c.uncertainty):
            self.offset = c.offset
        p = inputs.get("path")
        obj = inputs.get("object")
        if obj is not None:
            self.obj_states[obj.state] = self.obj_states.get(obj.state, 0) + 1
        if p is None:
            return None
        if p.frame_idx == getattr(self, "_last_idx", None) and p.valid == getattr(
            self, "_last_valid", None
        ):
            return None
        self._last_idx, self._last_valid = p.frame_idx, p.valid
        now = time.time()
        lat = None
        if p.frame_idx >= 0:
            if self.live and self.offset is not None:
                lat = now - (p.t + self.offset)
            elif self.t0_wall is not None and not self.live:
                lat = now - (self.t0_wall + p.t)
        if p.valid:
            self.valid_times.append(now)
            self.first_valid_wall = self.first_valid_wall or now
            if lat is not None and 0 <= lat < 30:
                self.lat.append(lat)
        else:
            self.invalid_times.append(now)
        self.fh.write(
            json.dumps(
                {
                    "wall": now,
                    "t": p.t,
                    "idx": p.frame_idx,
                    "valid": bool(p.valid),
                    "length": float(p.length),
                    "lat": lat,
                }
            )
            + "\n"
        )
        self.fh.flush()
        return None

    def stats(self) -> dict:
        lat = np.array(self.lat) if self.lat else np.zeros(0)
        vt = np.array(self.valid_times)
        rate = None
        if len(vt) >= 2:
            rate = float((len(vt) - 1) / max(vt[-1] - vt[0], 1e-6))
        return {
            "n_valid_paths": len(self.valid_times),
            "n_invalid_paths": len(self.invalid_times),
            "valid_path_hz": rate,
            "first_valid_after_s": (self.first_valid_wall - self.t_start)
            if self.first_valid_wall
            else None,
            "e2e_capture_to_path_ms_p50": float(np.percentile(lat, 50) * 1e3) if len(lat) else None,
            "e2e_capture_to_path_ms_p95": float(np.percentile(lat, 95) * 1e3) if len(lat) else None,
            "n_latency": int(len(lat)),
            "object_states": self.obj_states,
            "valid_wall_times": [round(x - self.t_start, 2) for x in self.valid_times][-400:],
            "invalid_wall_times": [round(x - self.t_start, 2) for x in self.invalid_times][-100:],
        }

    def close(self) -> None:
        self.fh.close()


# ---------------------------------------------------------------------------- visualisation
class RerunLiveBlock:
    """Visualisation Rerun : `live` (visualiseur lancé), `file` (.rrd) ou les deux (`both`)."""

    def __init__(self, raw: dict) -> None:
        import rerun as rr

        self.rr = rr
        mode = str(raw.get("_rerun", "file"))
        rr.init("visionaid_live", spawn=False)
        out = resolve_path(raw["paths"]["outputs"]) / "live_session.rrd"
        out.parent.mkdir(parents=True, exist_ok=True)
        if mode == "both" and hasattr(rr, "set_sinks"):  # visualiseur + fichier
            rr.spawn(connect=False)
            rr.set_sinks(rr.GrpcSink(), rr.FileSink(str(out)))
        elif mode in ("live", "both"):
            rr.spawn(connect=True)
        else:
            rr.save(str(out))
        rr.log("world", rr.ViewCoordinates.RIGHT_HAND_Z_UP, static=True)
        self.traj: list[np.ndarray] = []
        self.n = 0
        self.last_cm = None
        self.last_path = None

    def process(self, inputs: dict[str, Any]) -> dict[str, Any] | None:
        rr = self.rr
        f = inputs.get("frame")
        if f is None:
            return None
        self.n += 1
        rr.set_time("t", duration=float(f.t))
        h, w = f.image.shape[:2]
        rr.log("camera/image", rr.Image(f.image[:, :, ::-1]).compress(jpeg_quality=70))
        d = inputs.get("detections")
        if d is not None and len(d.boxes):
            labels = [
                (d.labels[i] if i < len(d.labels) else "") + (" CIBLE" if i == d.target_idx else "")
                for i in range(len(d.boxes))
            ]
            colors = [
                [255, 140, 0] if i == d.target_idx else [160, 160, 160] for i in range(len(d.boxes))
            ]
            rr.log(
                "camera/image/detections",
                rr.Boxes2D(
                    array=d.boxes, array_format=rr.Box2DFormat.XYXY, labels=labels, colors=colors
                ),
            )
        pose = inputs.get("pose_world")
        if pose is not None:
            T = pose.T_world_cam
            rr.log("world/camera", rr.Transform3D(translation=T[:3, 3], mat3x3=T[:3, :3]))
            rr.log(
                "world/camera/image",
                rr.Pinhole(
                    image_from_camera=f.K, width=w, height=h, camera_xyz=rr.ViewCoordinates.RDF
                ),
            )
            self.traj.append(T[:3, 3].copy())
            if len(self.traj) > 1:
                rr.log("world/trajectory", rr.LineStrips3D([np.array(self.traj[-2000:])]))
            rr.log("status/pose_quality", rr.TextLog(pose.quality))
        cm = inputs.get("costmap")
        if cm is not None and cm is not self.last_cm and self.n % 5 == 0:
            from visionaid.mapping.costmap import FREE, OCC

            self.last_cm = cm
            img = np.full(cm.state.shape + (3,), 128, np.uint8)
            img[cm.state == FREE] = 255
            img[cm.state == OCC] = 0
            rr.log("costmap", rr.Image(img[::-1]))
        p = inputs.get("path")
        if p is not None and p is not self.last_path:
            self.last_path = p
            if p.valid and len(p.points) > 1:
                p3 = np.c_[p.points, np.full(len(p.points), 0.02)]
                rr.log("world/path", rr.LineStrips3D([p3], colors=[[0, 200, 0]]))
            else:
                rr.log("world/path", rr.Clear(recursive=False))
        obj = inputs.get("object")
        if obj is not None and np.isfinite(obj.position).all():
            rr.log(
                "world/target",
                rr.Points3D([obj.position], colors=[[255, 140, 0]], radii=0.08, labels=[obj.state]),
            )
        return None

    def close(self) -> None:
        try:
            self.rr.disconnect()
        except Exception:
            pass
