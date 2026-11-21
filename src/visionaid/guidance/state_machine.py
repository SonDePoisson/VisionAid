"""Machine à états du guidage, avec priorités, hystérésis et temps de maintien minimal."""

from __future__ import annotations

import math
from dataclasses import dataclass

SEARCHING = "SEARCHING"
NAVIGATING = "NAVIGATING"
APPROACHING = "APPROACHING"
ARRIVED = "ARRIVED"
OBSTACLE_ALERT = "OBSTACLE_ALERT"
TRACKING_LOST = "TRACKING_LOST"
STATES = (SEARCHING, NAVIGATING, APPROACHING, ARRIVED, OBSTACLE_ALERT, TRACKING_LOST)


@dataclass
class GuidanceInputs:
    """Entrées résumées d'un cycle de guidage."""

    t: float
    pose_lost: bool = False
    object_known: bool = False
    distance: float = math.inf  # distance horizontale tête → objet (m)
    obstacle_dist: float = math.inf  # obstacle le plus proche dans le cône frontal (m)
    path_valid: bool = False


class GuidanceStateMachine:
    """Priorités : TRACKING_LOST > OBSTACLE_ALERT > ARRIVED > APPROACHING > NAVIGATING > SEARCHING.

    Chaque seuil a une hystérésis (sortie à seuil + `hysteresis_m`) et aucun changement d'état
    n'a lieu moins de `min_state_dwell_s` après le précédent (y compris les alertes : latence
    d'alerte ≤ temps de maintien).
    """

    def __init__(self, cfg_guidance) -> None:
        g = cfg_guidance
        self.approach = float(g.approach_m)
        self.arrived = float(g.arrived_m)
        self.obstacle = float(g.obstacle_m)
        self.hyst = float(g.hysteresis_m)
        self.dwell = float(g.min_state_dwell_s)
        self.state = SEARCHING
        self.t_change = -math.inf
        self.history: list[tuple[float, str]] = [(-math.inf, SEARCHING)]

    def _desired(self, x: GuidanceInputs) -> str:
        s = self.state
        if x.pose_lost:
            return TRACKING_LOST
        alert_th = self.obstacle + (self.hyst if s == OBSTACLE_ALERT else 0.0)
        near_target = x.object_known and x.distance < self.approach
        # près de la cible, le meuble qui la porte n'est pas un obstacle à signaler ; en recherche
        # (objet inconnu) l'utilisateur tourne sur place : pas d'alerte
        if x.obstacle_dist < alert_th and x.object_known and not near_target:
            return OBSTACLE_ALERT
        if not x.object_known:
            return SEARCHING
        arr_th = self.arrived + (self.hyst if s == ARRIVED else 0.0)
        app_th = self.approach + (self.hyst if s in (APPROACHING, ARRIVED) else 0.0)
        if x.distance < arr_th:
            return ARRIVED
        if x.distance < app_th:
            return APPROACHING
        return NAVIGATING

    def step(self, x: GuidanceInputs) -> str:
        want = self._desired(x)
        if want != self.state and x.t - self.t_change >= self.dwell:
            self.state = want
            self.t_change = x.t
            self.history.append((x.t, want))
        return self.state
