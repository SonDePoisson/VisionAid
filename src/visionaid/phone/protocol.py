"""Protocole téléphone → PC (version 1) : constantes, (dé)codage des images et des lots IMU.

Voir `docs/protocol.md`.
"""

from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass

import numpy as np

from visionaid.bus.messages import ImuBatch

PROTOCOL_VERSION = 1
SUPPORTED_VERSIONS = {1}
GYRO_UNITS = {"deg/s": math.pi / 180.0, "rad/s": 1.0}


class ProtocolError(ValueError):
    """Message mal formé ou version inconnue."""


@dataclass
class FramePacket:
    """Image reçue : en-tête + JPEG brut."""

    seq: int
    t_phone: float
    w: int
    h: int
    calib: bool
    jpeg: bytes


def pack_frame(seq: int, t_phone: float, w: int, h: int, jpeg: bytes, calib: bool = False) -> bytes:
    """Construit un message binaire d'image (côté téléphone ; utilisé par le faux téléphone)."""
    hdr = json.dumps(
        {"type": "frame", "seq": seq, "t_phone": t_phone, "w": w, "h": h, "calib": calib}
    ).encode()
    return struct.pack(">I", len(hdr)) + hdr + jpeg


def unpack_frame(data: bytes) -> FramePacket:
    """Décode un message binaire d'image."""
    if len(data) < 4:
        raise ProtocolError("message binaire trop court")
    (n,) = struct.unpack(">I", data[:4])
    if n <= 0 or 4 + n > len(data):
        raise ProtocolError("longueur d'en-tête invalide")
    try:
        hdr = json.loads(data[4 : 4 + n].decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ProtocolError(f"en-tête illisible : {e}") from e
    if hdr.get("type") != "frame":
        raise ProtocolError("type d'en-tête inattendu")
    jpeg = data[4 + n :]
    if not jpeg:
        raise ProtocolError("image vide")
    try:
        return FramePacket(
            int(hdr["seq"]),
            float(hdr["t_phone"]),
            int(hdr["w"]),
            int(hdr["h"]),
            bool(hdr.get("calib", False)),
            jpeg,
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ProtocolError(f"en-tête incomplet : {e}") from e


def check_hello(msg: dict) -> None:
    """Vérifie le message `hello` (version, unités du gyroscope)."""
    if msg.get("type") != "hello":
        raise ProtocolError("le premier message doit être « hello »")
    v = msg.get("protocol")
    if v not in SUPPORTED_VERSIONS:
        raise ProtocolError(
            f"version de protocole {v!r} non prise en charge (attendu : {sorted(SUPPORTED_VERSIONS)})"
        )
    if msg.get("gyro_units", "deg/s") not in GYRO_UNITS:
        raise ProtocolError(f"unité de gyroscope inconnue : {msg.get('gyro_units')!r}")


def imu_batch_from_json(
    samples: list, gyro_units: str = "deg/s", t_recv: float | None = None
) -> ImuBatch:
    """Lot IMU JSON `[[t, gx, gy, gz, ax, ay, az], …]` → `ImuBatch` (gyro en rad/s).

    Les lignes incomplètes ou non finies sont ignorées (capteur absent un instant).
    """
    rows = []
    for s in samples:
        if not isinstance(s, (list, tuple)) or len(s) < 7:
            continue
        try:
            r = [float(x) for x in s[:7]]
        except (TypeError, ValueError):
            continue
        if all(math.isfinite(x) for x in r):
            rows.append(r)
    if not rows:
        return ImuBatch(np.zeros(0), np.zeros((0, 3)), np.zeros((0, 3)), t_recv)
    a = np.asarray(rows, float)
    a = a[np.argsort(a[:, 0], kind="stable")]
    k = GYRO_UNITS[gyro_units]
    return ImuBatch(a[:, 0].copy(), a[:, 1:4] * k, a[:, 4:7].copy(), t_recv)
