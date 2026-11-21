"""Rendu hors ligne des consignes en piste stéréo (WAV), avec les sons de `assets/sounds`.

Exécute les `SoundCommand` de `audio.director` exactement comme le téléphone :
- guide : `guide_notes` note(s) de direction_2, fondu d'entrée et extinction exponentielle,
  répétée tous les `interval_s`, spatialisée (ITD/ILD paramétriques, `audio.binaural`) ;
- alerte : son grave non spatialisé, répété tous les `alert_period_s` ;
- arrivée : joué une fois, non spatialisé ;
- halo : réverbération légère, identique sur les deux oreilles (ne déplace pas la direction).

Le téléphone utilise le rendu HRTF du navigateur ; ici la spatialisation est paramétrique
(sans fichier HRTF), donc proche mais pas identique.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from visionaid.audio.binaural import smooth_azimuth, spatialize
from visionaid.audio.director import ALERT, GUIDE, SEARCH, SOUND_KEYS, SoundDirector
from visionaid.bus.messages import GuidanceCue, SoundCommand
from visionaid.utils.config import resolve_path
from visionaid.utils.logging import get_logger

log = get_logger("audio")
HALO_HIGHPASS_HZ = 700.0


def db_lin(db: float) -> float:
    return 10.0 ** (float(db) / 20.0)


def load_sound(path: str | Path, fs: int) -> np.ndarray:
    """WAV → float64 (N, C) au taux `fs`."""
    import soundfile as sf

    x, sr = sf.read(str(path), always_2d=True)
    if sr != fs:
        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(int(sr), int(fs))
        x = resample_poly(x, fs // g, sr // g, axis=0)
    return np.asarray(x, np.float64)


def guide_note(x: np.ndarray, fs: int, notes: int, note_s: float, fade_in: float, fade_out: float):
    """Mono : les `notes` premières notes, fondu d'entrée linéaire, extinction exponentielle."""
    m = x.mean(axis=1)
    n = len(m) if notes >= 5 else min(len(m), int(round(notes * note_s * fs)))
    y = m[:n].copy()
    ni = min(int(fade_in * fs), n // 3)
    if ni > 0:
        y[:ni] *= np.arange(ni) / ni
    no = min(int(fade_out * fs), n // 2)
    if no > 0:  # comme setTargetAtTime(0, …, fade_out / 5) du téléphone
        y[n - no :] *= np.exp(-np.arange(no) / (fade_out / 5 * fs))
    return y


def halo_ir(fs: int, seconds: float = 0.9, seed: int = 0) -> np.ndarray:
    """Réponse impulsionnelle synthétique (même forme que sur le téléphone), énergie 1.

    Mono, appliquée à l'identique aux deux oreilles, et sans graves (passe-haut 700 Hz) : sur une
    note grave, un halo qui garde la fondamentale interfère avec le son direct et peut faire
    pencher le volume du mauvais côté (jusqu'à 3,5 dB). La fondamentale, qui porte la direction
    (décalage entre les oreilles), reste ainsi intacte.
    """
    from scipy.signal import butter, lfilter

    rng = np.random.default_rng(seed)
    n = int(round(seconds * fs))
    t = np.arange(n) / fs
    ir = lfilter([0.25], [1, -0.75], rng.uniform(-1, 1, n))  # aigus amortis
    ir *= np.exp(-t / 0.25) * np.minimum(1.0, t / 0.01)
    b, a = butter(2, HALO_HIGHPASS_HZ / (fs / 2), "high")
    ir = lfilter(b, a, ir)
    return ir / np.sqrt((ir**2).sum())


class AudioRenderer:
    """Convertit une suite de consignes horodatées en piste stéréo synchronisée."""

    def __init__(self, cfg_audio) -> None:
        a = cfg_audio
        self.cfg = a
        self.fs = int(a.sample_rate)
        self.head_radius = float(a.head_radius_m)
        self.c = float(a.speed_of_sound)
        self.tau = float(a.smoothing_s)
        self.back_hz = float(a.back_lowpass_hz)
        self.alert_period = float(a.alert_period_s)
        self.halo = float(a.halo_mix)
        self.master = db_lin(a.master_gain_db)
        snd = a.sounds
        d = resolve_path(a.sounds_dir)
        self.sounds = {
            k: load_sound(d / getattr(snd, k).file, self.fs) * db_lin(getattr(snd, k).gain_db)
            for k in SOUND_KEYS
        }
        self.guide = guide_note(
            self.sounds["guide"],
            self.fs,
            int(a.guide_notes),
            float(a.guide_note_s),
            float(a.guide_fade_in_s),
            float(a.guide_fade_out_s),
        )
        # exploration : le son `search` entier, avec de courts fondus (timbre distinct du guide)
        self.search = guide_note(self.sounds["search"], self.fs, 5, 1.0, 0.01, 0.15)

    def director(self) -> SoundDirector:
        return SoundDirector(self.cfg)

    def interval(self, distance: float) -> float:
        """Espacement entre deux notes du guide à cette distance (s)."""
        return SoundDirector(self.cfg).interval(distance)

    @staticmethod
    def _add(buf: np.ndarray, i: int, x: np.ndarray) -> None:
        if i >= len(buf) or i + len(x) <= 0:
            return
        a, b = max(i, 0), min(i + len(x), len(buf))
        buf[a:b] += x[a - i : b - i]

    def commands(self, cues: list[GuidanceCue]) -> list[SoundCommand]:
        d = self.director()
        return [d.command(c) for c in sorted(cues, key=lambda c: c.t)]

    def render(self, cues: list[GuidanceCue], t0: float, duration: float) -> np.ndarray:
        """Piste stéréo float32 (N, 2) de durée `duration` commençant à `t0`."""
        fs = self.fs
        n = int(round(duration * fs))
        spatial = np.zeros(n)
        diotic = np.zeros((n, 2))
        az = np.zeros(n)
        bgain = np.ones(n)
        cmds = self.commands(cues)
        next_note: float | None = None
        next_alert: float | None = None
        for k, c in enumerate(cmds):
            ta = c.t
            tb = cmds[k + 1].t if k + 1 < len(cmds) else t0 + duration
            ia = max(int(round((ta - t0) * fs)), 0)
            ib = min(int(round((tb - t0) * fs)), n)
            if ib > ia:
                az[ia:ib] = c.azimuth_render
                bgain[ia:ib] = db_lin(c.back_gain_db)
            if c.mode in (GUIDE, SEARCH):
                if next_note is None:
                    next_note = ta
                while next_note < tb:
                    i = int(round((next_note - t0) * fs))
                    note = self.search if c.mode == SEARCH else self.guide
                    self._add(spatial, i, note * db_lin(c.gain_db))
                    next_note += c.interval_s
            else:
                next_note = None
            if k + 1 < len(cmds) and (cmds[k + 1].mode == SEARCH) != (c.mode == SEARCH):
                next_note = None  # passage recherche ↔ guidage : nouveau rythme immédiatement
            if c.mode == ALERT:
                if next_alert is None:
                    next_alert = ta
                while next_alert < tb:
                    self._add(diotic, int(round((next_alert - t0) * fs)), self.sounds["alert"])
                    next_alert += self.alert_period
            else:
                next_alert = None
            if c.event == "arrived":
                self._add(diotic, int(round((ta - t0) * fs)), self.sounds["arrived"])
        if n == 0:
            return np.zeros((0, 2), np.float32)
        # gains et direction lissés : aucun clic aux changements
        from scipy.signal import fftconvolve, lfilter

        kk = math.exp(-1.0 / (max(self.tau, 1e-3) * fs))
        bgain = lfilter([1 - kk], [1, -kk], bgain, zi=[bgain[0] * kk])[0]
        azs = smooth_azimuth(az, fs, self.tau)
        st = spatialize(spatial * bgain, azs, fs, self.head_radius, self.c, self.back_hz)
        if self.halo > 0 and spatial.any():
            st += self.halo * fftconvolve(spatial, halo_ir(fs))[:n, None]
        st = (st + diotic) * self.master
        peak = float(np.abs(st).max())
        if peak > 0.98:
            log.warning("Piste trop forte (crête %.2f) : ramenée à 0,98", peak)
            st *= 0.98 / peak
        return st.astype(np.float32)

    def write_wav(self, path: str | Path, stereo: np.ndarray) -> None:
        import soundfile as sf

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), stereo, self.fs, subtype="PCM_16")
