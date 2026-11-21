"""Bloc source du bus alimenté par le téléphone : dernière image + IMU accumulée depuis l'appel précédent."""

from __future__ import annotations

import threading
import time
from typing import Any

import numpy as np

from visionaid.bus.messages import ClockSync, Frame, ImuBatch
from visionaid.phone.server import PhoneServer
from visionaid.utils.config import _to_dataclass


def merge_batches(batches: list[ImuBatch]) -> ImuBatch | None:
    """Concatène des lots IMU (triés par temps), ou None si vide."""
    batches = [b for b in batches if len(b)]
    if not batches:
        return None
    t = np.concatenate([b.t for b in batches])
    o = np.argsort(t, kind="stable")
    return ImuBatch(
        t[o],
        np.concatenate([b.gyro for b in batches])[o],
        np.concatenate([b.accel for b in batches])[o],
        batches[-1].t_recv,
    )


class PhoneInbox:
    """Tampon thread-safe entre le serveur (rappels) et un consommateur synchrone.

    Ne garde que la **dernière** image (pas d'accumulation de retard), mais toute l'IMU.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._frame: Frame | None = None
        self._imu: list[ImuBatch] = []
        self._clock: ClockSync | None = None
        self.n_frames_in = 0
        self.n_frames_out = 0
        self.n_overwritten = 0

    def put_frame(self, f: Frame) -> None:
        with self._cond:
            if self._frame is not None:
                self.n_overwritten += 1
            self._frame = f
            self.n_frames_in += 1
            self._cond.notify_all()

    def put_imu(self, b: ImuBatch) -> None:
        with self._cond:
            self._imu.append(b)

    def put_clock(self, c: ClockSync) -> None:
        with self._cond:
            self._clock = c

    def get(self, timeout: float = 0.1) -> tuple[Frame | None, ImuBatch | None, ClockSync | None]:
        """Attend une nouvelle image (au plus `timeout`) ; renvoie (image, IMU, horloge)."""
        with self._cond:
            if self._frame is None:
                self._cond.wait(timeout)
            f, self._frame = self._frame, None
            imu, self._imu = merge_batches(self._imu), []
            c, self._clock = self._clock, None
            if f is not None:
                self.n_frames_out += 1
            return f, imu, c


class PhoneSourceBlock:
    """Source du graphe temps réel : démarre le serveur et publie `frame`, `imu`, `clock`."""

    def __init__(self, raw: dict, record: str | None = None) -> None:
        cfg = _to_dataclass("config", raw)
        self.inbox = PhoneInbox()
        rec = record if record is not None else raw.get("_phone_record")
        self.server = PhoneServer(
            cfg,
            on_frame=self.inbox.put_frame,
            on_imu=self.inbox.put_imu,
            on_clock=self.inbox.put_clock,
            record=rec,
            https_port=raw.get("_phone_https_port"),
            http_port=raw.get("_phone_http_port"),
            meta=raw.get("_phone_meta"),
        ).start()
        self.t_start = time.time()

    def process(self, inputs: dict[str, Any]) -> dict[str, Any] | None:
        f, imu, c = self.inbox.get(0.05)
        out: dict[str, Any] = {}
        if imu is not None:  # l'IMU part avant l'image qu'elle précède
            out["imu"] = imu
        if c is not None:
            out["clock"] = c
        if f is not None:
            out["frame"] = f
        return out or None

    def stats(self) -> dict:
        s = self.server.summary()
        s.update(
            frames_in=self.inbox.n_frames_in,
            frames_out=self.inbox.n_frames_out,
            overwritten=self.inbox.n_overwritten,
        )
        return s

    def close(self) -> None:
        self.server.stop()
