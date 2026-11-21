"""Choix du son à jouer à partir d'une consigne de guidage.

Toute la logique sonore est ici, en un seul endroit : le téléphone (Web Audio) et le rendu hors
ligne (WAV) ne font qu'exécuter les `SoundCommand` produites.

- recherche → note du guide plus douce, qui balaie ;
- navigation, approche → note du guide spatialisée vers l'objectif, espacement réduit en
  approchant ;
- obstacle, repérage perdu → son grave « arrête-toi », non spatialisé, répété ;
- arrivée → son d'arrivée une fois (`event`), puis silence.

Direction : exagération des petits angles g(x) = x + (k − 1)/2 · sin 2x, monotone pour k ≤ 2,
qui conserve 0°, ±90° et 180° (devant reste devant, derrière reste derrière). Derrière (au-delà de
90°, complètement à partir de 120°), le son est assourdi et un peu plus faible.
"""

from __future__ import annotations

import math

import numpy as np

from visionaid.bus.messages import GuidanceCue, SoundCommand

SILENT, SEARCH, GUIDE, ALERT, ARRIVED = "silent", "search", "guide", "alert", "arrived"
STATE_MODE = {
    "SEARCHING": SEARCH,
    "NAVIGATING": GUIDE,
    "APPROACHING": GUIDE,
    "ARRIVED": ARRIVED,
    "OBSTACLE_ALERT": ALERT,
    "TRACKING_LOST": ALERT,
}
LOWPASS_OFF_HZ = 20000.0


def expand_azimuth(az, k: float):
    """Exagère les petits angles (k = 1 : identité). Scalaire ou tableau, en radians."""
    k = float(np.clip(k, 1.0, 2.0))
    return az + (k - 1.0) / 2.0 * np.sin(2.0 * np.asarray(az, float))


def backness(az):
    """0 devant et sur les côtés (jusqu'à 90°), 1 à partir de 120° ; continu."""
    return np.clip(-2.0 * np.cos(np.asarray(az, float)), 0.0, 1.0)


class SoundDirector:
    """Convertit les `GuidanceCue` successives en `SoundCommand`."""

    def __init__(self, cfg_audio) -> None:
        a = cfg_audio
        self.far_s = float(a.guide_interval_far_s)
        self.near_s = float(a.guide_interval_near_s)
        self.far_m = float(a.guide_far_m)
        self.search_db = float(a.search_gain_db)
        self.k = float(a.azimuth_expansion)
        self.back_hz = float(a.back_lowpass_hz)
        self.back_db = float(a.back_gain_db)
        self.cooldown = float(a.arrived_cooldown_s)
        self.prev_mode: str | None = None
        self.t_arrived = -math.inf

    def interval(self, distance: float) -> float:
        """Espacement entre deux notes : `far` au loin, réduit linéairement jusqu'à `near`."""
        if not math.isfinite(distance):
            return self.far_s
        x = float(np.clip(distance / self.far_m, 0.0, 1.0))
        return self.near_s + (self.far_s - self.near_s) * x

    def command(self, cue: GuidanceCue) -> SoundCommand:
        mode = STATE_MODE.get(cue.state, SILENT)
        az = float(cue.azimuth) if mode in (SEARCH, GUIDE) else 0.0
        azr = float(expand_azimuth(az, self.k))
        b = float(backness(azr))
        lp = LOWPASS_OFF_HZ * (self.back_hz / LOWPASS_OFF_HZ) ** b if self.back_hz < 2e4 else 2e4
        event = ""
        if (
            mode == ARRIVED
            and self.prev_mode != ARRIVED
            and cue.t - self.t_arrived >= self.cooldown
        ):
            event = ARRIVED
            self.t_arrived = cue.t
        self.prev_mode = mode
        return SoundCommand(
            t=float(cue.t),
            frame_idx=int(cue.frame_idx),
            state=cue.state,
            mode=mode,
            azimuth=az,
            azimuth_render=azr,
            distance=float(cue.distance),
            interval_s=self.far_s if mode == SEARCH else self.interval(cue.distance),
            gain_db=self.search_db if mode == SEARCH else 0.0,
            lowpass_hz=float(lp),
            back_gain_db=self.back_db * b,
            event=event,
        )
