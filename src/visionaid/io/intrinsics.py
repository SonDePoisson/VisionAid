"""Intrinsèques caméra : K par défaut depuis un champ de vision, ou calibration OpenCV."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml


@dataclass
class Intrinsics:
    """Modèle sténopé sans distorsion."""

    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int

    @property
    def K(self) -> np.ndarray:
        return np.array([[self.fx, 0, self.cx], [0, self.fy, self.cy], [0, 0, 1]], dtype=np.float64)

    def scaled(self, width: int, height: int) -> Intrinsics:
        """Intrinsèques pour une image redimensionnée."""
        sx, sy = width / self.width, height / self.height
        return Intrinsics(self.fx * sx, self.fy * sy, self.cx * sx, self.cy * sy, width, height)

    def rotated90(self, clockwise: bool = True) -> Intrinsics:
        """Intrinsèques après rotation de l'image de 90°."""
        if clockwise:
            return Intrinsics(
                self.fy, self.fx, self.height - self.cy, self.cx, self.height, self.width
            )
        return Intrinsics(self.fy, self.fx, self.cy, self.width - self.cx, self.height, self.width)


def from_hfov(
    width: int, height: int, hfov_deg: float, landscape_reference: bool = True
) -> Intrinsics:
    """K à partir d'un champ de vision horizontal.

    Si `landscape_reference`, le champ est rapporté au plus grand côté (orientation capteur),
    ce qui reste correct pour une vidéo tournée en portrait.
    """
    ref = max(width, height) if landscape_reference else width
    f = (ref / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
    return Intrinsics(f, f, width / 2.0, height / 2.0, width, height)


def load_calibration(path: str | Path) -> Intrinsics:
    """Charge une calibration OpenCV (npz avec K, width, height ; ou yaml avec camera_matrix)."""
    p = Path(path)
    if p.suffix == ".npz":
        d = np.load(p)
        K = np.asarray(d["K"], dtype=np.float64)
        w, h = int(d["width"]), int(d["height"])
    else:
        d = yaml.safe_load(p.read_text())
        K = np.asarray(d.get("K", d.get("camera_matrix")), dtype=np.float64).reshape(3, 3)
        w, h = int(d["width"]), int(d["height"])
    return Intrinsics(K[0, 0], K[1, 1], K[0, 2], K[1, 2], w, h)


def make_intrinsics(cfg_intr, width: int, height: int) -> Intrinsics:
    """Intrinsèques pour une image (width, height) selon la config."""
    if getattr(cfg_intr, "calibration_file", None):
        return load_calibration(cfg_intr.calibration_file).scaled(width, height)
    return from_hfov(width, height, float(cfg_intr.hfov_deg))
