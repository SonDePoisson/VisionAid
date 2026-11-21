"""Sources d'images : fichier vidéo, replay temps réel, liste en mémoire, stub WebRTC."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Protocol, runtime_checkable

import cv2
import numpy as np

from visionaid.bus.messages import Frame
from visionaid.io.intrinsics import Intrinsics, from_hfov, make_intrinsics


@runtime_checkable
class FrameSource(Protocol):
    """Contrat d'une source d'images horodatées."""

    @property
    def intrinsics(self) -> Intrinsics: ...

    @property
    def fps(self) -> float: ...

    def read(self) -> Frame | None: ...


def rotate_image(img: np.ndarray, rotation_deg: int) -> np.ndarray:
    """Rotation d'affichage (sens horaire) multiple de 90°."""
    r = int(rotation_deg) % 360
    if r == 90:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if r == 180:
        return cv2.rotate(img, cv2.ROTATE_180)
    if r == 270:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img


class VideoFileSource:
    """Lit un fichier vidéo : rotation selon métadonnées, redimensionnement, timestamps vidéo."""

    def __init__(
        self,
        path: str | Path,
        width: int | None = 640,
        apply_rotation: bool = True,
        rotation_override: int | None = None,
        cfg_intrinsics=None,
        start_frame: int = 0,
        max_frames: int | None = None,
    ) -> None:
        self.path = Path(path)
        self.cap = cv2.VideoCapture(str(self.path))
        if not self.cap.isOpened():
            raise OSError(f"Impossible d'ouvrir {self.path}")
        self.cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 0)
        meta_rot = int(self.cap.get(cv2.CAP_PROP_ORIENTATION_META))
        self.rotation = (
            (rotation_override if rotation_override is not None else meta_rot)
            if apply_rotation
            else 0
        )
        self._fps = float(self.cap.get(cv2.CAP_PROP_FPS)) or 30.0
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w0 = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h0 = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if self.rotation % 180 == 90:
            w0, h0 = h0, w0
        self.out_w = int(width) if width else w0
        self.out_h = int(round(h0 * self.out_w / w0))
        if cfg_intrinsics is not None:
            self._intr = make_intrinsics(cfg_intrinsics, self.out_w, self.out_h)
        else:
            self._intr = from_hfov(self.out_w, self.out_h, 69.0)
        self.max_frames = max_frames
        self._idx = 0
        self._last_t = -1.0
        if start_frame > 0:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            self._idx = start_frame
        self._start = start_frame

    @classmethod
    def from_config(cls, cfg, path: str | Path | None = None, **kw) -> VideoFileSource:
        from visionaid.utils.config import resolve_path

        return cls(
            resolve_path(path or cfg.paths.video),
            width=cfg.video.width,
            apply_rotation=cfg.video.apply_rotation,
            cfg_intrinsics=cfg.intrinsics,
            **kw,
        )

    @property
    def intrinsics(self) -> Intrinsics:
        return self._intr

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def duration(self) -> float:
        return self.frame_count / self._fps

    def read(self) -> Frame | None:
        if self.max_frames is not None and self._idx - self._start >= self.max_frames:
            return None
        ok, img = self.cap.read()
        if not ok:
            return None
        t = self.cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        if not np.isfinite(t) or t <= self._last_t:
            t = self._idx / self._fps  # fallback : index / fps
            if t <= self._last_t:
                t = self._last_t + 1.0 / self._fps
        self._last_t = t
        img = rotate_image(img, self.rotation)
        if img.shape[1] != self.out_w or img.shape[0] != self.out_h:
            img = cv2.resize(img, (self.out_w, self.out_h), interpolation=cv2.INTER_AREA)
        fr = Frame(t=float(t), frame_idx=self._idx, image=img, K=self._intr.K)
        self._idx += 1
        return fr

    def close(self) -> None:
        self.cap.release()

    def __iter__(self):
        while (f := self.read()) is not None:
            yield f


class ListSource:
    """Source en mémoire (tests, lecture inversée)."""

    def __init__(self, frames: list[Frame], intrinsics: Intrinsics, fps: float = 30.0) -> None:
        self.frames = list(frames)
        self._intr = intrinsics
        self._fps = fps
        self._i = 0

    @property
    def intrinsics(self) -> Intrinsics:
        return self._intr

    @property
    def fps(self) -> float:
        return self._fps

    def read(self) -> Frame | None:
        if self._i >= len(self.frames):
            return None
        f = self.frames[self._i]
        self._i += 1
        return f


class ReplaySource:
    """Débite une source au rythme réel ; si le consommateur est en retard, saute des frames."""

    def __init__(
        self, source: FrameSource, speed: float = 1.0, clock=time.perf_counter, sleep=time.sleep
    ) -> None:
        self.src = source
        self.speed = float(speed)
        self._clock = clock
        self._sleep = sleep
        self._pending: Frame | None = None
        self._t0: float | None = None
        self._wall0 = 0.0
        self.skipped = 0
        self.delivered = 0

    @property
    def intrinsics(self) -> Intrinsics:
        return self.src.intrinsics

    @property
    def fps(self) -> float:
        return self.src.fps

    def _due(self, f: Frame) -> float:
        return self._wall0 + (f.t - self._t0) / self.speed

    def read(self) -> Frame | None:
        frame = self._pending if self._pending is not None else self.src.read()
        self._pending = None
        if frame is None:
            return None
        if self._t0 is None:
            self._t0 = frame.t
            self._wall0 = self._clock()
            self.delivered += 1
            return frame
        wait = self._due(frame) - self._clock()
        if wait > 0:
            self._sleep(wait)
            self.delivered += 1
            return frame
        # En retard : on saute toutes les frames déjà échues sauf la plus récente.
        while True:
            nxt = self.src.read()
            if nxt is None:
                break
            if self._due(nxt) <= self._clock():
                self.skipped += 1
                frame = nxt
                continue
            self._pending = nxt
            break
        self.delivered += 1
        return frame


class WebRTCSource:
    """Stub : flux du téléphone via WebRTC (à venir).

    Contrat attendu : `read()` renvoie une `Frame` dont `t` est l'horodatage capteur du téléphone
    (horloge commune avec la pose ARKit), `K` les intrinsèques ARKit de la frame ; la pose associée
    est publiée par `ArkitPoseSource` avec le même `t`/`frame_idx`. Les frames trop anciennes sont
    abandonnées (dernière valeur seulement).
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError("WebRTCSource n'est pas encore implémentée")
