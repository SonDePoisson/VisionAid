"""Synchronisation d'horloge téléphone ↔ PC par ping/pong (style NTP simplifié)."""

from __future__ import annotations

import math
from collections import OrderedDict, deque

from visionaid.bus.messages import ClockSync


class ClockEstimator:
    """Estime `offset` tel que t_pc ≈ t_phone + offset.

    Chaque ping `id` donne d = t_pc_reçu − t_phone_envoyé = offset + délai aller. Le téléphone
    mesure le RTT de cet échange au retour du pong et le renvoie avec le ping suivant
    (`prev_id`, `rtt`). On apparie d et RTT du **même** échange ; sur une fenêtre glissante, on
    retient l'échange de RTT minimal : offset = d − RTT/2, incertitude RTT/2. Sans RTT apparié,
    offset = min(d) (biaisé du délai aller minimal), avec une incertitude par défaut.
    """

    def __init__(self, window: int = 30, default_uncertainty: float = 0.05) -> None:
        self.samples: deque[tuple[float, float, float]] = deque(maxlen=window)
        self.raw: deque[tuple[float, float]] = deque(maxlen=window)
        self.pending: OrderedDict = OrderedDict()
        self.default_uncertainty = default_uncertainty

    def ping(self, ping_id, t_phone: float, t_pc: float) -> None:
        """Enregistre la réception d'un ping."""
        d = t_pc - t_phone
        self.raw.append((t_pc, d))
        if ping_id is not None:
            self.pending[ping_id] = (t_pc, d)
            while len(self.pending) > 64:
                self.pending.popitem(last=False)

    def rtt(self, ping_id, rtt: float | None) -> None:
        """Associe le RTT mesuré par le téléphone au ping `ping_id`."""
        if ping_id is None or rtt is None or not math.isfinite(rtt) or rtt < 0:
            return
        hit = self.pending.pop(ping_id, None)
        if hit is not None:
            self.samples.append((hit[0], hit[1], float(rtt)))

    def estimate(self, t: float = 0.0) -> ClockSync:
        """Estimation à partir des échanges de la fenêtre."""
        if self.samples:
            _, d, r = min(self.samples, key=lambda s: s[2])
            return ClockSync(t, d - r / 2.0, r / 2.0, r)
        if self.raw:
            d = min(d for _, d in self.raw)
            return ClockSync(t, d, self.default_uncertainty, 0.0)
        return ClockSync(t, 0.0, math.inf, 0.0)
