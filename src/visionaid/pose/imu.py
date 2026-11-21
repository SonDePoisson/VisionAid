"""IMU pour la pose : tampon corrigé (unités, biais, rotation, décalage) et filtre de gravité.

Convention temporelle (phase 17) : l'image horodatée t correspond à l'instant IMU t + δ. Le tampon
stocke les échantillons dans le **temps image** (t_imu − δ) et dans le **repère caméra**.
"""

from __future__ import annotations

import math

import numpy as np

from visionaid.bus.messages import ImuBatch
from visionaid.calib.device import ImuCalib
from visionaid.calib.rotation import so3_exp

G = 9.81


class ImuBuffer:
    """Échantillons IMU corrigés, exprimés dans le repère caméra et le temps image."""

    def __init__(self, calib: ImuCalib, keep_s: float = 10.0, extrapolate_s: float = 0.05) -> None:
        self.R = np.asarray(calib.R_cam_imu, float)
        # accéléromètre : rotation et signe propres (Safari iOS : axes du gyroscope permutés,
        # signe de l'accéléromètre inversé ; les deux sont mesurés par la calibration)
        R_acc = getattr(calib, "R_cam_acc", None)
        self.R_acc = np.asarray(R_acc, float) if R_acc is not None else self.R
        self.acc_sign = float(getattr(calib, "accel_sign", 1.0))
        self.bias = np.asarray(calib.gyro_bias, float)
        self.delta = float(calib.time_offset_s)
        self.units = float(calib.units_fix)
        self.keep_s = keep_s
        self.extra = extrapolate_s
        self.t = np.zeros(0)
        self.w = np.zeros((0, 3))  # rad/s, repère caméra
        self.a = np.zeros((0, 3))  # m/s², repère caméra (gravité incluse : +g vers le haut)

    def __len__(self) -> int:
        return len(self.t)

    def add(self, batch: ImuBatch | None) -> None:
        """Ajoute un lot (horloge téléphone, repère appareil, gyro dans l'unité annoncée)."""
        if batch is None or len(batch) == 0:
            return
        t = np.asarray(batch.t, float) - self.delta
        w = (np.asarray(batch.gyro, float) * self.units - self.bias) @ self.R.T
        a = self.acc_sign * np.asarray(batch.accel, float) @ self.R_acc.T
        if len(self.t):
            keep = t > self.t[-1]
            t, w, a = t[keep], w[keep], a[keep]
        self.t = np.r_[self.t, t]
        self.w = np.r_[self.w, w]
        self.a = np.r_[self.a, a]
        if len(self.t) and self.t[-1] - self.t[0] > self.keep_s:
            i = int(np.searchsorted(self.t, self.t[-1] - self.keep_s))
            self.t, self.w, self.a = self.t[i:], self.w[i:], self.a[i:]

    def covers(self, t0: float, t1: float) -> bool:
        return len(self.t) >= 2 and t0 >= self.t[0] - self.extra and t1 <= self.t[-1] + self.extra

    def delta_R(self, t0: float, t1: float) -> np.ndarray | None:
        """Rotation caméra R_c0_c1 entre les instants image t0 et t1 (intégration du gyroscope)."""
        if t1 <= t0:
            return np.eye(3)
        if not self.covers(t0, t1):
            return None
        t, w = self.t, self.w
        inside = (t > t0) & (t < t1)
        ts = np.r_[t0, t[inside], t1]
        ws = np.stack([np.interp(ts, t, w[:, k]) for k in range(3)], 1)
        R = np.eye(3)
        for k in range(len(ts) - 1):
            R = R @ so3_exp(0.5 * (ws[k] + ws[k + 1]) * (ts[k + 1] - ts[k]))
        return R

    def accel_mean(self, t0: float, t1: float) -> tuple[np.ndarray | None, float]:
        """Accélération moyenne (repère caméra) sur [t0, t1] et son écart-type de norme."""
        if not len(self.t):
            return None, math.inf
        m = (self.t >= t0) & (self.t <= t1)
        if m.sum() < 2:
            return None, math.inf
        a = self.a[m]
        return a.mean(0), float(np.linalg.norm(a, axis=1).std())

    def rate_deg_s(self, t0: float, t1: float) -> float:
        """Vitesse angulaire maximale (deg/s) sur [t0, t1]."""
        m = (self.t >= t0) & (self.t <= t1)
        if not m.any():
            return 0.0
        return float(np.degrees(np.linalg.norm(self.w[m], axis=1).max()))


class GravityFilter:
    """Direction « haut » dans le repère caméra : propagée par le gyroscope, corrigée par l'accéléromètre.

    Au repos, l'accéléromètre (gravité incluse) mesure +g selon le haut. La correction n'est
    appliquée que si la norme est proche de g (marche modérée), avec un gain faible.
    """

    def __init__(self, gain: float = 0.05, tolerance: float = 1.5) -> None:
        self.up: np.ndarray | None = None
        self.gain = gain
        self.tol = tolerance
        self.n_corrections = 0

    @property
    def ready(self) -> bool:
        return self.up is not None

    def init(self, acc_mean: np.ndarray | None) -> bool:
        if acc_mean is None:
            return False
        n = float(np.linalg.norm(acc_mean))
        if abs(n - G) > self.tol:
            return False
        self.up = acc_mean / n
        return True

    def predict(self, R_prev_cur: np.ndarray | None) -> None:
        """La caméra a tourné de R_prev_cur : le vecteur fixe « haut » change de coordonnées."""
        if self.up is not None and R_prev_cur is not None:
            u = R_prev_cur.T @ self.up
            self.up = u / np.linalg.norm(u)

    def correct(self, acc_mean: np.ndarray | None, acc_std: float = 0.0) -> None:
        if self.up is None or acc_mean is None:
            return
        n = float(np.linalg.norm(acc_mean))
        if abs(n - G) > self.tol or acc_std > 2.0:
            return
        u = (1 - self.gain) * self.up + self.gain * acc_mean / n
        self.up = u / np.linalg.norm(u)
        self.n_corrections += 1


def gravity_aligned_rotation(up_cam: np.ndarray) -> np.ndarray:
    """R_world_cam initiale : z monde = haut, x monde = axe optique projeté à l'horizontale."""
    z = np.asarray(up_cam, float) / np.linalg.norm(up_cam)
    fwd = np.array([0.0, 0.0, 1.0])
    x = fwd - np.dot(fwd, z) * z
    if np.linalg.norm(x) < 1e-6:  # caméra pointée vers le haut ou le bas
        x = np.array([1.0, 0.0, 0.0]) - z[0] * z
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return np.stack([x, y, z])  # lignes = axes monde exprimés en repère caméra
