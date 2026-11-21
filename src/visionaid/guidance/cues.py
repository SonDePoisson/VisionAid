"""Calcul des consignes de guidage (azimut/élévation relatifs à la tête, distance, messages)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from visionaid.bus.messages import Costmap, GuidanceCue, ObjectEstimate, Path, Pose
from visionaid.guidance.state_machine import (
    APPROACHING,
    ARRIVED,
    NAVIGATING,
    OBSTACLE_ALERT,
    SEARCHING,
    TRACKING_LOST,
    GuidanceInputs,
    GuidanceStateMachine,
)
from visionaid.mapping.costmap import OCC

MESSAGES = {
    SEARCHING: "Tournez lentement sur place",
    NAVIGATING: "Suivez le son",
    APPROACHING: "Vous approchez, tendez la main",
    ARRIVED: "Vous êtes arrivé",
    OBSTACLE_ALERT: "Attention, obstacle devant",
    TRACKING_LOST: "Arrêtez-vous, repérage perdu",
}


def head_frame(T_world_head: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(position, avant horizontal, gauche horizontal) de la tête dans le monde (z haut)."""
    pos = T_world_head[:3, 3]
    fwd = T_world_head[:3, 2].copy()  # axe optique
    fwd[2] = 0.0
    if np.linalg.norm(fwd) < 1e-6:  # regard vertical : on prend −y caméra
        fwd = -T_world_head[:3, 1].copy()
        fwd[2] = 0.0
    fwd /= np.linalg.norm(fwd)
    left = np.cross([0.0, 0.0, 1.0], fwd)
    return pos, fwd, left


def relative_direction(T_world_head: np.ndarray, p_world: np.ndarray) -> tuple[float, float, float]:
    """(azimut gauche+, élévation haut+, distance horizontale) d'un point monde."""
    pos, fwd, left = head_frame(T_world_head)
    p = np.asarray(p_world, float)
    if p.shape[0] == 2:  # point au sol sans hauteur : à hauteur de tête (élévation nulle)
        p = np.array([p[0], p[1], pos[2]])
    v = p - pos
    hd = float(math.hypot(v[0], v[1]))
    az = math.atan2(float(v @ left), float(v @ fwd))
    el = math.atan2(float(v[2]), max(hd, 1e-6))
    return az, el, hd


def frontal_obstacle(
    cm: Costmap | None,
    T_world_head: np.ndarray,
    max_dist: float,
    cone_deg: float,
    half_width: float = np.inf,
) -> tuple[float, float]:
    """Distance et azimut de l'obstacle occupé le plus proche dans le cône frontal (inf si aucun).

    `half_width` restreint au couloir balayé par le corps (|écart latéral| < half_width) : un
    obstacle sur le côté d'un chemin dégagé ne déclenche pas d'alerte.
    """
    if cm is None:
        return math.inf, 0.0
    pos, fwd, left = head_frame(T_world_head)
    r = int(math.ceil(max_dist / cm.resolution)) + 1
    ci = int(math.floor((pos[1] - cm.origin[1]) / cm.resolution))
    cj = int(math.floor((pos[0] - cm.origin[0]) / cm.resolution))
    h, w = cm.state.shape
    a0, a1, b0, b1 = max(ci - r, 0), min(ci + r + 1, h), max(cj - r, 0), min(cj + r + 1, w)
    if a0 >= a1 or b0 >= b1:
        return math.inf, 0.0
    ii, jj = np.nonzero(cm.state[a0:a1, b0:b1] == OCC)
    if len(ii) == 0:
        return math.inf, 0.0
    x = cm.origin[0] + (jj + b0 + 0.5) * cm.resolution - pos[0]
    y = cm.origin[1] + (ii + a0 + 0.5) * cm.resolution - pos[1]
    d = np.hypot(x, y)
    lat = x * left[0] + y * left[1]
    az = np.arctan2(lat, x * fwd[0] + y * fwd[1])
    m = (np.abs(az) <= math.radians(cone_deg)) & (d <= max_dist) & (np.abs(lat) < half_width)
    if not m.any():
        return math.inf, 0.0
    k = int(np.argmin(np.where(m, d, np.inf)))
    return float(d[k]), float(az[k])


class GuidanceEngine:
    """Combine pose, objet, chemin et costmap en une consigne `GuidanceCue`."""

    def __init__(self, cfg) -> None:
        g = cfg.guidance
        self.sm = GuidanceStateMachine(g)
        # tête = torse (hypothèse du hackathon) : `body.T_cam_body` prime sur `guidance.T_cam_head`
        body = getattr(cfg, "body", None)
        T = getattr(body, "T_cam_body", None) if body is not None else None
        self.T_cam_head = np.asarray(T if T is not None else g.T_cam_head, float)
        self.cone = float(g.obstacle_cone_deg)
        self.obstacle_m = float(g.obstacle_m)
        self.corridor = float(g.obstacle_corridor_m)
        self.final_m = float(g.final_direct_m)
        self.arrived_floor = float(g.arrived_m) + float(g.hysteresis_m) + 0.01
        self.approach_lookahead = float(g.approach_lookahead_m)
        self.voice_interval = float(g.voice_min_interval_s)
        self.t_voice = -math.inf
        self.last_state = None
        self.sweep_rate = math.radians(float(cfg.sim.sweep_rate_dps))
        self.messages: list[tuple[float, str]] = []

    def voice(self, t: float, state: str) -> str:
        """Message court au changement d'état, au plus un toutes les `voice_min_interval_s`."""
        if state == self.last_state:
            return ""
        if t - self.t_voice < self.voice_interval:
            return ""
        self.last_state = state
        self.t_voice = t
        msg = MESSAGES[state]
        self.messages.append((t, msg))
        return msg

    def update(
        self,
        t: float,
        frame_idx: int,
        pose: Pose | None,
        obj: ObjectEstimate | None,
        path: Path | None,
        cm: Costmap | None,
    ) -> GuidanceCue:
        lost = pose is None or pose.quality == "lost"
        T_head = None if pose is None else pose.T_world_cam @ self.T_cam_head
        known = obj is not None and obj.state != "unknown" and np.isfinite(obj.position).all()
        dist = math.inf
        obst_d, obst_az = math.inf, 0.0
        if T_head is not None:
            if known:
                _, _, dist = relative_direction(T_head, obj.position)
                if (
                    obj.state == "candidate"
                ):  # cible probable : jamais « arrivé » avant confirmation
                    dist = max(dist, self.arrived_floor)
            obst_d, obst_az = frontal_obstacle(
                cm, T_head, self.obstacle_m + 0.3, self.cone, self.corridor
            )
        x = GuidanceInputs(t, lost, known, dist, obst_d, path is not None and path.valid)
        state = self.sm.step(x)
        az = el = 0.0
        alert = 0.0
        if T_head is not None:
            if state == NAVIGATING:
                target = (
                    path.lookahead
                    if (path is not None and path.valid and np.isfinite(path.lookahead).all())
                    else obj.position[:2]
                )
                az, _, _ = relative_direction(T_head, target)
            elif state in (APPROACHING, ARRIVED):
                az, el, _ = relative_direction(T_head, obj.position)
                # approche : on suit la fin du chemin (dégagée) tant que le but est à plus de
                # `final_direct_m`, puis guidage direct vers l'objet (évite les coins de meubles)
                if (
                    state == APPROACHING
                    and path is not None
                    and path.valid
                    and len(path.points) > 1
                ):
                    from visionaid.planning.lookahead import lookahead_point

                    head_xy = T_head[:2, 3]
                    if np.linalg.norm(path.goal - head_xy) > self.final_m:
                        az, _, _ = relative_direction(
                            T_head, lookahead_point(path.points, self.approach_lookahead)
                        )
            elif state == OBSTACLE_ALERT:
                az = obst_az
                alert = (
                    float(np.clip(1.0 - obst_d / max(self.obstacle_m, 1e-6), 0.0, 1.0))
                    if math.isfinite(obst_d)
                    else 1.0
                )
            elif state == SEARCHING:
                az = math.radians(60.0) * math.sin(self.sweep_rate * t)  # consigne de balayage lent
        if state == TRACKING_LOST:
            alert = 1.0
        return GuidanceCue(
            t, frame_idx, state, float(az), float(el), float(dist), alert, self.voice(t, state)
        )

    # interface Block du bus
    def process(self, inputs: dict[str, Any]) -> dict[str, Any] | None:
        pose = inputs.get("pose_world") or inputs.get("pose")
        if pose is None:
            return None
        return {
            "cue": self.update(
                pose.t,
                pose.frame_idx,
                pose,
                inputs.get("object"),
                inputs.get("path"),
                inputs.get("costmap"),
            )
        }
