"""Préparation des sons de guidage : coupe des silences, fondus, mono, volume perçu égalisé.

Les fichiers d'origine (`assets/sounds/*.wav`) ne sont jamais modifiés ; les versions préparées
sont écrites dans `assets/sounds/processed/` avec un rapport `levels.json`.

Volume perçu : sonie BS.1770 (pondération K) maximale sur une fenêtre glissante de 400 ms
(« sonie momentanée »), ramenée à `target_lufs` ; crête limitée à `peak_dbfs`.

    uv run python -m visionaid.audio.prepare
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from visionaid.utils.config import resolve_path

# sons spatialisés : passés en mono (la spatialisation ajoute la stéréo)
SOUNDS = {
    "direction_1.wav": {"mono": True},
    "direction_2.wav": {"mono": True},
    "vous_etes_arrive.wav": {"mono": False},
    "zone_spaciale_grave.wav": {"mono": False},
}


def _biquad_shelf(fs: float) -> tuple[np.ndarray, np.ndarray]:
    """Étage 1 de la pondération K (plateau aigu +4 dB), BS.1770, pour toute fréquence."""
    G, Q, fc = 3.999843853973347, 0.7071752369554196, 1681.974450955533
    A = 10 ** (G / 40)
    w0 = 2 * math.pi * fc / fs
    alpha = math.sin(w0) / (2 * Q)
    c = math.cos(w0)
    b = np.array(
        [
            A * ((A + 1) + (A - 1) * c + 2 * math.sqrt(A) * alpha),
            -2 * A * ((A - 1) + (A + 1) * c),
            A * ((A + 1) + (A - 1) * c - 2 * math.sqrt(A) * alpha),
        ]
    )
    a = np.array(
        [
            (A + 1) - (A - 1) * c + 2 * math.sqrt(A) * alpha,
            2 * ((A - 1) - (A + 1) * c),
            (A + 1) - (A - 1) * c - 2 * math.sqrt(A) * alpha,
        ]
    )
    return b / a[0], a / a[0]


def _biquad_highpass(fs: float) -> tuple[np.ndarray, np.ndarray]:
    """Étage 2 de la pondération K (passe-haut ~38 Hz)."""
    Q, fc = 0.5003270373238773, 38.13547087602444
    w0 = 2 * math.pi * fc / fs
    alpha = math.sin(w0) / (2 * Q)
    c = math.cos(w0)
    b = np.array([(1 + c) / 2, -(1 + c), (1 + c) / 2])
    a = np.array([1 + alpha, -2 * c, 1 - alpha])
    return b / a[0], a / a[0]


def momentary_loudness(x: np.ndarray, fs: int, window_s: float = 0.4) -> float:
    """Sonie momentanée maximale (LUFS) ; `x` (N,) ou (N, C)."""
    from scipy.signal import lfilter

    x = x.reshape(len(x), -1)
    b1, a1 = _biquad_shelf(fs)
    b2, a2 = _biquad_highpass(fs)
    y = lfilter(b2, a2, lfilter(b1, a1, x, axis=0), axis=0)
    n = max(1, int(window_s * fs))
    p = np.sum(y**2, axis=1)  # canaux sommés (poids 1, BS.1770)
    if len(p) < n:
        p = np.pad(p, (0, n - len(p)))
    c = np.concatenate([[0.0], np.cumsum(p)])
    ms = (c[n:] - c[:-n]) / n  # moyenne glissante (somme cumulée : O(N))
    return float(-0.691 + 10 * math.log10(max(ms.max(), 1e-12)))


def trim(x: np.ndarray, fs: int, thresh_db: float = -50.0, pre_s: float = 0.005) -> np.ndarray:
    """Retire le silence au début et à la fin (seuil relatif à la crête de l'enveloppe 10 ms)."""
    m = np.abs(x.reshape(len(x), -1)).max(axis=1)
    n = max(1, int(0.01 * fs))
    env = np.sqrt(np.convolve(m**2, np.ones(n) / n, mode="same"))
    on = np.nonzero(env > env.max() * 10 ** (thresh_db / 20))[0]
    if len(on) == 0:
        return x
    a = max(0, on[0] - int(pre_s * fs))
    b = min(len(x), on[-1] + n)
    return x[a:b]


def fades(x: np.ndarray, fs: int, fade_in_s: float = 0.004, fade_out_s: float = 0.03):
    """Fondus en cosinus surélevé (aucun clic au début ni à la fin)."""
    x = x.copy()
    for n, rev in ((int(fade_in_s * fs), False), (int(fade_out_s * fs), True)):
        n = min(n, len(x) // 2)
        if n <= 0:
            continue
        w = 0.5 - 0.5 * np.cos(np.pi * np.arange(n) / n)
        if rev:
            x[-n:] *= w[::-1].reshape(-1, *([1] * (x.ndim - 1)))
        else:
            x[:n] *= w.reshape(-1, *([1] * (x.ndim - 1)))
    return x


def prepare_one(
    x: np.ndarray, fs: int, mono: bool, target_lufs: float, peak_dbfs: float
) -> tuple[np.ndarray, dict]:
    x = np.asarray(x, np.float64)
    if x.ndim == 1:
        x = x[:, None]
    before = {"lufs_m": momentary_loudness(x, fs), "dur_s": len(x) / fs}
    if mono:
        x = x.mean(axis=1, keepdims=True)
    x = fades(trim(x, fs), fs)
    gain_db = target_lufs - momentary_loudness(x, fs)
    x = x * 10 ** (gain_db / 20)
    peak = float(np.abs(x).max())
    lim = 10 ** (peak_dbfs / 20)
    if peak > lim:  # crête trop haute : on baisse (le son sera un peu moins fort que la cible)
        x *= lim / peak
    after = {
        "lufs_m": momentary_loudness(x, fs),
        "peak_dbfs": float(20 * math.log10(np.abs(x).max() + 1e-12)),
        "dur_s": len(x) / fs,
        "channels": int(x.shape[1]),
    }
    return (x[:, 0] if mono else x), {"before": before, "after": after, "gain_db": gain_db}


def main(argv=None) -> dict:
    import soundfile as sf

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default="assets/sounds")
    ap.add_argument("--dst", default="assets/sounds/processed")
    ap.add_argument("--target-lufs", type=float, default=-20.0)
    ap.add_argument("--peak-dbfs", type=float, default=-1.0)
    a = ap.parse_args(argv)
    src, dst = resolve_path(a.src), resolve_path(a.dst)
    dst.mkdir(parents=True, exist_ok=True)
    report = {"target_lufs": a.target_lufs, "peak_dbfs": a.peak_dbfs, "sounds": {}}
    for name, opt in SOUNDS.items():
        p = Path(src) / name
        if not p.exists():
            continue
        x, fs = sf.read(str(p), always_2d=True)
        y, info = prepare_one(x, fs, opt["mono"], a.target_lufs, a.peak_dbfs)
        sf.write(str(dst / name), y, fs, subtype="PCM_16")
        report["sounds"][name] = info
        print(
            f"{name:28s} {info['before']['lufs_m']:6.1f} → {info['after']['lufs_m']:6.1f} LUFS  "
            f"crête {info['after']['peak_dbfs']:5.1f} dBFS  {info['after']['dur_s']:.2f} s"
        )
    (dst / "levels.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    main()
