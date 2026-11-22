"""Choix du son à jouer à partir d'une consigne de guidage.

Toute la logique sonore est ici, en un seul endroit : le téléphone (Web Audio) et le rendu hors
ligne (WAV) ne font qu'exécuter les `SoundCommand` produites.

Deux couches superposées, pour que l'utilisateur entende en même temps où aller et ce qui gêne :

- **chemin** (son 2) : note répétée, placée par un pan stéréo vers la direction du chemin ; le
  tempo accélère à l'approche de la cible. Objet pas encore trouvé : son de recherche (son 4) ;
- **obstacles** (son 1) : nappe en boucle, centrée, de plus en plus forte quand un obstacle du
  couloir frontal se rapproche (plafonnée sous le chemin, pour ne pas stresser) ;
- **arrivée** (son 3) : une fois, puis silence ;
- **repérage perdu** : plus de chemin, nappe des obstacles à volume moyen (« arrête-toi »).

Pan (comme le panoramique d'une table de mixage) : pan = azimut / 90°, borné à ±1 ; à ±1 tout
le son est dans une seule oreille. Chemin derrière : tout d'un côté, celui du demi-tour le plus
court, gardé tant que le chemin ne passe pas franchement de l'autre côté (hystérésis autour de
180°, sinon le son sauterait d'une oreille à l'autre).
"""

from __future__ import annotations

import math

import numpy as np

from visionaid.bus.messages import GuidanceCue, SoundCommand

SILENT, SEARCH, GUIDE, LOST, ARRIVED = "silent", "search", "guide", "lost", "arrived"
STATE_MODE = {
    "SEARCHING": SEARCH,
    "NAVIGATING": GUIDE,
    "APPROACHING": GUIDE,
    "OBSTACLE_ALERT": GUIDE,  # le chemin continue ; l'obstacle est la couche du dessus
    "ARRIVED": ARRIVED,
    "TRACKING_LOST": LOST,
}
MUTE_DB = -120.0
SOUND_KEYS = ("guide", "search", "arrived", "obstacle")  # sons de `audio.sounds`


def equal_power(pan):
    """Gains (gauche, droite) à puissance constante ; pan −1 → (1, 0), 0 → (0,707, 0,707)."""
    th = (np.clip(np.asarray(pan, float), -1.0, 1.0) + 1.0) * math.pi / 4
    return np.cos(th), np.sin(th)


class PanTracker:
    """Azimut (rad, gauche +) → pan (−1 gauche … +1 droite), avec hystérésis derrière."""

    def __init__(self, hold_deg: float = 150.0) -> None:
        self.hold = math.radians(float(hold_deg))
        self.side = 0.0  # côté retenu quand le chemin est derrière : +1 gauche, −1 droite

    def __call__(self, az: float) -> float:
        az = math.atan2(math.sin(az), math.cos(az))
        if abs(az) <= math.pi / 2:
            self.side = 0.0
            return float(np.clip(-az / (math.pi / 2), -1.0, 1.0))
        s = 1.0 if az > 0 else -1.0
        if self.side == 0.0 or (s != self.side and abs(az) < self.hold):
            self.side = s  # entrée derrière, ou chemin passé franchement de l'autre côté
        return -self.side

    def reset(self) -> None:
        self.side = 0.0


class SoundDirector:
    """Convertit les `GuidanceCue` successives en `SoundCommand`."""

    def __init__(self, cfg_audio) -> None:
        a = cfg_audio
        self.far_s = float(a.guide_interval_far_s)
        self.near_s = float(a.guide_interval_near_s)
        self.accel_m = float(a.guide_accel_m)
        self.near_m = float(a.guide_near_m)
        self.search_s = float(a.search_interval_s)
        self.ob_far = float(a.obstacle_far_m)
        self.ob_near = float(a.obstacle_near_m)
        self.ob_min = float(a.obstacle_min_db)
        self.ob_max = float(a.obstacle_max_db)
        self.lost_db = float(a.lost_obstacle_db)
        self.cooldown = float(a.arrived_cooldown_s)
        self.pan = PanTracker(float(a.back_hold_deg))
        self.prev_mode: str | None = None
        self.t_arrived = -math.inf

    def interval(self, distance: float) -> float:
        """Espacement entre deux notes du chemin : constant au loin, puis de plus en plus court
        sous `guide_accel_m`, jusqu'à `guide_interval_near_s` à `guide_near_m`."""
        if not math.isfinite(distance):
            return self.far_s
        x = float(np.clip((distance - self.near_m) / max(self.accel_m - self.near_m, 1e-6), 0, 1))
        return self.near_s + (self.far_s - self.near_s) * x

    def obstacle_db(self, distance: float) -> float:
        """Gain de la nappe des obstacles : muette au-delà de `obstacle_far_m`, puis linéaire en
        dB jusqu'à `obstacle_max_db` à `obstacle_near_m`."""
        if not math.isfinite(distance) or distance >= self.ob_far:
            return MUTE_DB
        x = float(np.clip((self.ob_far - distance) / max(self.ob_far - self.ob_near, 1e-6), 0, 1))
        return self.ob_min + (self.ob_max - self.ob_min) * x

    def command(self, cue: GuidanceCue) -> SoundCommand:
        mode = STATE_MODE.get(cue.state, SILENT)
        az = float(getattr(cue, "guide_azimuth", math.nan))
        if not math.isfinite(az):  # consigne sans direction du chemin (anciens enregistrements)
            az = float(cue.azimuth) if cue.state != "OBSTACLE_ALERT" else 0.0
        if mode in (SEARCH, GUIDE):
            pan = self.pan(az)
        else:
            pan, az = 0.0, 0.0
            self.pan.reset()
        if mode == GUIDE:
            ob = self.obstacle_db(float(getattr(cue, "obstacle_distance", math.inf)))
        elif mode == LOST:
            ob = self.lost_db
        else:
            ob = MUTE_DB
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
            pan=float(pan),
            distance=float(cue.distance),
            interval_s=self.search_s if mode == SEARCH else self.interval(cue.distance),
            gain_db=0.0,
            obstacle_db=float(ob),
            event=event,
        )
