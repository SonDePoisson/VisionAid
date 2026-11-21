"""Blocs minimaux pour tester le bus (importables par les sous-processus)."""

from __future__ import annotations

import time

import numpy as np

from visionaid.bus.messages import Frame, GuidanceCue


class CounterSource:
    """Publie des frames numérotées à cadence fixe."""

    def __init__(self, cfg: dict) -> None:
        self.i = 0
        self.size = tuple(cfg.get("test_size", (48, 64, 3)))

    def process(self, inputs):
        f = Frame(t=time.time(), frame_idx=self.i, image=np.full(self.size, self.i % 255, np.uint8))
        self.i += 1
        return {"frame": f}


class SlowEcho:
    """Consomme les frames lentement et renvoie un cue avec l'index reçu."""

    def __init__(self, cfg: dict) -> None:
        self.delay = float(cfg.get("test_delay", 0.05))

    def process(self, inputs):
        f = inputs.get("frame")
        if f is None:
            return None
        time.sleep(self.delay)
        return {"cue": GuidanceCue(t=f.t, frame_idx=f.frame_idx, state="TEST")}


class Collector:
    """Puits silencieux."""

    def __init__(self, cfg: dict) -> None:
        self.n = 0

    def process(self, inputs):
        self.n += 1
        return None

    def stats(self):
        return {"n": self.n}
