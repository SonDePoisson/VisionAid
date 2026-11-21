"""Messages échangés entre les blocs (dataclasses) et leur (dé)sérialisation msgpack."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

import msgpack
import msgpack_numpy
import numpy as np


@dataclass
class Frame:
    """Image BGR uint8 horodatée avec ses intrinsèques."""

    t: float
    frame_idx: int
    image: np.ndarray
    K: np.ndarray = field(default_factory=lambda: np.eye(3))
    t_phone: float | None = None  # instant de saisie, horloge du téléphone (s)
    t_recv: float | None = None  # instant de réception, horloge du PC (s, time.time())


@dataclass
class Pose:
    """Pose caméra T_world_cam (4×4 float64) et qualité de suivi."""

    t: float
    frame_idx: int
    T_world_cam: np.ndarray
    quality: str = "ok"  # ok | lost | init
    n_inliers: int = 0
    reproj_err: float = 0.0
    is_keyframe: bool = False


@dataclass
class Depth:
    """Profondeur métrique (m) à la résolution de l'image."""

    t: float
    frame_idx: int
    depth: np.ndarray
    confidence: np.ndarray | None = None


@dataclass
class Detections:
    """Détections d'une frame, avec pistes et décision « cible »."""

    t: float
    frame_idx: int
    boxes: np.ndarray  # (N,4) xyxy en pixels
    scores: np.ndarray  # (N,)
    labels: list[str] = field(default_factory=list)
    masks: np.ndarray | None = None  # (N,H,W) bool
    track_ids: np.ndarray | None = None  # (N,) int
    reid_scores: np.ndarray | None = None  # (N,)
    target_idx: int = -1  # index de la détection confirmée comme cible, -1 sinon
    target_track_id: int = -1


@dataclass
class ObjectEstimate:
    """Position monde estimée de la cible et son état de mémoire."""

    t: float
    frame_idx: int
    position: np.ndarray  # (3,)
    cov: np.ndarray  # (3,3)
    state: str = "unknown"  # unknown | seen | remembered | stale
    confidence: float = 0.0


@dataclass
class Costmap:
    """Grille 2D vue de dessus : état (−1 inconnu, 0 libre, 1 occupé) et coût."""

    t: float
    frame_idx: int
    state: np.ndarray  # (H,W) int8
    cost: np.ndarray  # (H,W) float32, inf = interdit
    origin: np.ndarray  # (2,) coin (x,y) monde de la cellule (0,0)
    resolution: float = 0.05


@dataclass
class Path:
    """Chemin planifié en coordonnées monde (x,y)."""

    t: float
    frame_idx: int
    points: np.ndarray  # (N,2)
    lookahead: np.ndarray  # (2,)
    goal: np.ndarray  # (2,)
    valid: bool = False
    length: float = 0.0


@dataclass
class GuidanceCue:
    """Consigne de guidage relative à la tête."""

    t: float
    frame_idx: int
    state: str
    azimuth: float = 0.0  # rad, positif à gauche
    elevation: float = 0.0  # rad, positif vers le haut
    distance: float = float("nan")
    alert_level: float = 0.0
    message: str = ""


@dataclass
class ImuSample:
    """Échantillon inertiel, repère appareil (W3C : x droite, y haut de l'écran, z vers l'utilisateur)."""

    t: float  # horloge du téléphone (s)
    gyro: np.ndarray  # (3,) rad/s
    accel: np.ndarray  # (3,) m/s², gravité incluse
    accel_lin: np.ndarray | None = None  # (3,) m/s², sans gravité (si fourni)


@dataclass
class ImuBatch:
    """Lot d'échantillons inertiels en tableaux (plus compact sur le bus)."""

    t: np.ndarray  # (N,) horloge du téléphone (s)
    gyro: np.ndarray  # (N,3) rad/s
    accel: np.ndarray  # (N,3) m/s²
    t_recv: float | None = None  # réception côté PC

    @staticmethod
    def from_samples(samples: list[ImuSample], t_recv: float | None = None) -> ImuBatch:
        """Assemble des échantillons en lot."""
        if not samples:
            return ImuBatch(np.zeros(0), np.zeros((0, 3)), np.zeros((0, 3)), t_recv)
        return ImuBatch(
            np.array([s.t for s in samples], float),
            np.array([s.gyro for s in samples], float).reshape(-1, 3),
            np.array([s.accel for s in samples], float).reshape(-1, 3),
            t_recv,
        )

    def samples(self) -> list[ImuSample]:
        """Découpe le lot en échantillons."""
        return [
            ImuSample(float(t), g, a) for t, g, a in zip(self.t, self.gyro, self.accel, strict=True)
        ]

    def __len__(self) -> int:
        return len(self.t)


@dataclass
class ClockSync:
    """Décalage d'horloge : t_pc ≈ t_phone + offset (s), avec incertitude (demi-RTT minimal)."""

    t: float
    offset: float
    uncertainty: float
    rtt: float = 0.0


MESSAGE_TYPES: dict[str, type] = {
    c.__name__: c
    for c in (
        Frame,
        Pose,
        Depth,
        Detections,
        ObjectEstimate,
        Costmap,
        Path,
        GuidanceCue,
        ImuSample,
        ImuBatch,
        ClockSync,
    )
}


def _default(obj: Any) -> Any:
    if isinstance(obj, np.generic):
        return obj.item()
    return msgpack_numpy.encode(obj)


def encode(msg: Any) -> bytes:
    """Sérialise un message (dataclass) en msgpack."""
    payload = {f.name: getattr(msg, f.name) for f in dataclasses.fields(msg)}
    return msgpack.packb(
        {"_type": type(msg).__name__, "d": payload}, default=_default, use_bin_type=True
    )


def decode(data: bytes) -> Any:
    """Désérialise un message msgpack en dataclass."""
    obj = msgpack.unpackb(data, object_hook=msgpack_numpy.decode, raw=False)
    cls = MESSAGE_TYPES[obj["_type"]]
    return cls(**obj["d"])
