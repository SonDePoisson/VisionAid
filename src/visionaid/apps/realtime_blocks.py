"""Blocs du graphe temps réel (importables par les sous-processus du bus)."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

import numpy as np

from visionaid.bus.messages import Frame
from visionaid.utils.config import _to_dataclass, resolve_path


def _cfg(raw: dict):
    return _to_dataclass("config", raw)


class ReplaySourceBlock:
    """Lit la vidéo au rythme réel (en boucle) à partir de l'instant mural `_t0_wall`."""

    def __init__(self, raw: dict) -> None:
        from visionaid.io.sources import ReplaySource, VideoFileSource

        self.cfg = _cfg(raw)
        self.raw = raw
        self._mk = lambda: ReplaySource(
            VideoFileSource.from_config(self.cfg), float(self.cfg.replay.speed)
        )
        self.src = self._mk()
        self.offset_t = 0.0
        self.offset_idx = 0
        self.last: Frame | None = None
        self.loops = 0
        self.skipped = 0
        t0 = float(raw.get("_t0_wall", time.time()))
        while time.time() < t0:
            time.sleep(0.001)

    def process(self, inputs: dict[str, Any]) -> dict[str, Any] | None:
        f = self.src.read()
        if f is None:  # fin de vidéo : on reboucle (temps et index continus)
            self.skipped += self.src.skipped
            if self.last is not None:
                self.offset_t = self.last.t + 1.0 / self.src.fps
                self.offset_idx = self.last.frame_idx + 1
            self.loops += 1
            self.src = self._mk()
            f = self.src.read()
            if f is None:
                return None
        f = Frame(f.t + self.offset_t, f.frame_idx + self.offset_idx, f.image, f.K)
        self.last = f
        return {"frame": f}

    def stats(self) -> dict:
        return {"skipped_at_source": self.skipped + self.src.skipped, "loops": self.loops}


class SessionReplayBlock:
    """Rejoue une session téléphone au rythme réel (en boucle) : publie `frame` et `imu`.

    Les temps sont ramenés au début de la session (comme le temps vidéo de `ReplaySourceBlock`),
    images et IMU avec le même décalage ; `t_phone` garde l'horloge d'origine.
    """

    def __init__(self, raw: dict) -> None:
        from visionaid.io.session import SessionImu, SessionSource, load_session

        self.cfg = _cfg(raw)
        self.session = load_session(resolve_path(raw["_session"]))
        self.imu = SessionImu(self.session)
        self._mk = lambda: _replay(SessionSource.from_config(self.cfg, self.session.dir), self.cfg)
        self.src = self._mk()
        self.t_ref = self.session.frames[0]["t_phone"]
        self.offset_t = 0.0
        self.offset_idx = 0
        self.last: Frame | None = None
        self.last_t_phone: float | None = None
        self.loops = 0
        self.skipped = 0
        t0 = float(raw.get("_t0_wall", time.time()))
        while time.time() < t0:
            time.sleep(0.001)

    def process(self, inputs: dict[str, Any]) -> dict[str, Any] | None:
        from visionaid.bus.messages import ImuBatch

        f = self.src.read()
        if f is None:  # fin de session : on reboucle (temps et index continus, IMU repart)
            self.skipped += self.src.skipped
            if self.last is not None:
                self.offset_t = self.last.t + 1.0 / self.src.fps
                self.offset_idx = self.last.frame_idx + 1
            self.loops += 1
            self.last_t_phone = None
            self.src = self._mk()
            f = self.src.read()
            if f is None:
                return None
        shift = self.offset_t - self.t_ref
        imu = self.imu.window(self.last_t_phone, f.t)
        self.last_t_phone = f.t
        g = Frame(f.t + shift, f.frame_idx + self.offset_idx, f.image, f.K, f.t_phone, time.time())
        self.last = g
        out: dict[str, Any] = {}
        if len(imu):
            out["imu"] = ImuBatch(imu.t + shift, imu.gyro, imu.accel, time.time())
        out["frame"] = g
        return out

    def stats(self) -> dict:
        return {
            "skipped_at_source": self.skipped + self.src.skipped,
            "loops": self.loops,
            "session": self.session.name,
        }


def _replay(src, cfg):
    from visionaid.io.sources import ReplaySource

    return ReplaySource(src, float(cfg.replay.speed))


def make_perception(raw: dict):
    from visionaid.perception.pipeline import PerceptionBlock

    return PerceptionBlock(_cfg(raw))


class GeometryBlock:
    """Profondeur + odométrie visuelle sur la dernière frame disponible."""

    def __init__(self, raw: dict) -> None:
        from visionaid.perception.depth import DepthEstimator
        from visionaid.pose.source import make_pose_source

        cfg = _cfg(raw)
        self.depth = DepthEstimator(cfg)  # sans cache : latence réelle
        # VIO si la source publie l'IMU (téléphone, session) ; VO sinon (vidéo)
        self.vo = make_pose_source(cfg, bool(raw.get("_imu")))
        self.n = 0

    def process(self, inputs: dict[str, Any]) -> dict[str, Any] | None:
        from visionaid.pose.source import merge_imu

        if hasattr(self.vo, "add_imu"):
            self.vo.add_imu(merge_imu(inputs.get("imu")))
        f = inputs.get("frame")
        if f is None:
            return None
        d = self.depth(f)
        if hasattr(self.vo, "correct_depth"):
            d = self.vo.correct_depth(f, d)
        p = self.vo.update(f, d)
        self.n += 1
        return {"depth": d, "pose": p}

    def stats(self) -> dict:
        s = {"n": self.n, "lost_fraction": self.vo.lost_fraction}
        if hasattr(self.vo, "stats"):
            s.update(self.vo.stats())
        return s


class WorldBlock:
    """Modèle du monde ; associe chaque (profondeur, pose) aux détections de la même frame."""

    def __init__(self, raw: dict) -> None:
        from visionaid.mapping.world_model import WorldModel

        self.cfg = _cfg(raw)
        self.wm = WorldModel(self.cfg)
        # images du téléphone : intrinsèques de l'appareil (calibration de la phase 17)
        self.use_phone_intrinsics = bool(raw.get("_session") or raw.get("_phone"))
        self._K: dict = {}
        self.dets: OrderedDict = OrderedDict()
        self.n = 0
        self.n_with_dets = 0

    def process(self, inputs: dict[str, Any]) -> dict[str, Any] | None:
        from visionaid.bus.messages import Pose
        from visionaid.io.intrinsics import make_intrinsics

        det = inputs.get("detections")
        if det is not None:
            self.dets[det.frame_idx] = det
            while len(self.dets) > 60:
                self.dets.popitem(last=False)
        d, p = inputs.get("depth"), inputs.get("pose")
        if d is None or p is None or d.frame_idx != p.frame_idx:
            return None
        h, w = d.depth.shape
        if (w, h) not in self._K:
            if self.use_phone_intrinsics:
                from visionaid.calib.device import phone_intrinsics

                self._K[(w, h)] = phone_intrinsics(self.cfg, w, h).K
            else:
                self._K[(w, h)] = make_intrinsics(self.cfg.intrinsics, w, h).K
        K = self._K[(w, h)]
        frame = Frame(
            d.t, d.frame_idx, np.zeros((1, w, 3), np.uint8), K
        )  # seuls t, K et la largeur servent
        dets = self.dets.get(d.frame_idx)
        if dets is None and self.dets:
            # perception et géométrie traitent des frames différentes (conflation) : on accepte
            # la détection la plus proche à ±3 frames (≤ 100 ms)
            k = min(self.dets, key=lambda i: abs(i - d.frame_idx))
            if abs(k - d.frame_idx) <= 3:
                dets = self.dets[k]
        self.n += 1
        self.n_with_dets += dets is not None
        cm, obj = self.wm.update(frame, d, p, dets)
        out: dict[str, Any] = {"object": obj}
        if cm is not None:
            out["costmap"] = cm
            out["pose_world"] = Pose(
                p.t,
                p.frame_idx,
                self.wm.T_world_cam,
                p.quality,
                p.n_inliers,
                p.reproj_err,
                p.is_keyframe,
            )
        return out

    def stats(self) -> dict:
        return {"n": self.n, "with_detections": self.n_with_dets}


def make_planner(raw: dict):
    from visionaid.planning.planner import Planner

    return Planner(_cfg(raw))


def make_guidance(raw: dict):
    from visionaid.guidance.cues import GuidanceEngine

    return GuidanceEngine(_cfg(raw))


class CueSink:
    """Collecte les consignes : latence de bout en bout (capture → consigne), cadence."""

    def __init__(self, raw: dict) -> None:
        self.t0_wall = float(raw.get("_t0_wall", time.time()))
        self.lat: list[float] = []
        self.states: dict[str, int] = {}
        self.t_first = None
        self.t_last = None
        self.out = resolve_path(raw["paths"]["outputs"]) / "realtime_cues.jsonl"
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.out, "w")  # noqa: SIM115

    def process(self, inputs: dict[str, Any]) -> dict[str, Any] | None:
        import json

        c = inputs.get("cue")
        if c is None:
            return None
        now = time.time()
        self.t_first = self.t_first or now
        self.t_last = now
        self.n_all = getattr(self, "n_all", 0) + 1
        if c.frame_idx == getattr(self, "_last_idx", None):
            return None  # consigne répétée (minuteur 20 Hz) : latence comptée une seule fois
        self._last_idx = c.frame_idx
        self.lat.append(now - (self.t0_wall + c.t))
        self.states[c.state] = self.states.get(c.state, 0) + 1
        self.fh.write(
            json.dumps(
                {
                    "t": c.t,
                    "idx": c.frame_idx,
                    "state": c.state,
                    "az": c.azimuth,
                    "dist": c.distance if np.isfinite(c.distance) else None,
                    "lat": self.lat[-1],
                }
            )
            + "\n"
        )
        return None

    def close(self) -> None:
        self.fh.close()

    def stats(self) -> dict:
        a = np.asarray(self.lat) if self.lat else np.array([np.nan])
        span = (self.t_last - self.t_first) if self.t_first and self.t_last else 0.0
        return {
            "n_cues": len(self.lat),
            "e2e_p50_ms": float(np.nanpercentile(a, 50) * 1e3),
            "e2e_p95_ms": float(np.nanpercentile(a, 95) * 1e3),
            "cue_hz": getattr(self, "n_all", 0) / span if span > 0 else 0.0,
            "fresh_cue_hz": len(self.lat) / span if span > 0 else 0.0,
            "states": self.states,
        }
