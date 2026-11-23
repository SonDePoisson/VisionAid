"""Rendu hors ligne des consignes en piste stéréo (WAV), avec les sons de `assets/sounds`.

Exécute les `SoundCommand` de `audio.director` exactement comme le téléphone (`web/audio.js`) :
- chemin : note du son 2 (ou son 4 en recherche) répétée tous les `interval_s`, placée par un
  pan stéréo à puissance constante (pan −1 : tout à gauche, rien à droite) ;
- obstacles : nappe du son 1 en boucle, superposée, gain `obstacle_db` lissé ;
- arrivée : son 3 joué une fois, centré ;
- phrases (annonces) : synthèse macOS `say`, centrées, l'une après l'autre ; pendant une phrase
  « duck » (objet trouvé) la couche chemin est suspendue, comme sur le téléphone.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from visionaid.audio.director import GUIDE, MUTE_DB, SEARCH, SOUND_KEYS, SoundDirector, equal_power
from visionaid.bus.messages import GuidanceCue, SoundCommand
from visionaid.utils.config import resolve_path
from visionaid.utils.logging import get_logger

log = get_logger("audio")


def db_lin(db: float) -> float:
    return 0.0 if db <= MUTE_DB else 10.0 ** (float(db) / 20.0)


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


def _smooth(x: np.ndarray, fs: int, tau: float) -> np.ndarray:
    """Lissage exponentiel (premier ordre) d'un paramètre par échantillon."""
    if tau <= 0 or len(x) == 0:
        return x
    from scipy.signal import lfilter

    k = math.exp(-1.0 / (tau * fs))
    return lfilter([1 - k], [1, -k], x, zi=[x[0] * k])[0]


class AudioRenderer:
    """Convertit une suite de consignes horodatées en piste stéréo synchronisée."""

    def __init__(self, cfg_audio, cfg_tts=None, cache_dir=None) -> None:
        a = cfg_audio
        self.tts = cfg_tts
        self.tts_cache = cache_dir
        self.speeches: list[tuple[float, float, str]] = []  # (début, fin, texte) du dernier rendu
        self.cfg = a
        self.fs = int(a.sample_rate)
        self.tau = float(a.smoothing_s)
        self.tau_ob = float(a.obstacle_smoothing_s)
        self.master = db_lin(a.master_gain_db)
        snd = a.sounds
        d = resolve_path(a.sounds_dir)
        self.sounds = {
            k: load_sound(d / getattr(snd, k).file, self.fs) * db_lin(getattr(snd, k).gain_db)
            for k in SOUND_KEYS
        }
        self.guide = self.sounds["guide"].mean(axis=1)
        self.search = self.sounds["search"].mean(axis=1)
        ob = self.sounds["obstacle"]
        self.obstacle = ob if ob.shape[1] == 2 else np.repeat(ob, 2, axis=1)

    def director(self) -> SoundDirector:
        return SoundDirector(self.cfg)

    def interval(self, distance: float) -> float:
        """Espacement entre deux notes du chemin à cette distance (s)."""
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
        if n == 0:
            return np.zeros((0, 2), np.float32)
        notes = np.zeros(n)  # couche chemin (mono, pannée ensuite)
        center = np.zeros(n)  # arrivée (centrée)
        pan = np.zeros(n)
        ob_gain = np.zeros(n)
        cmds = self.commands(cues)
        next_note: float | None = None
        for k, c in enumerate(cmds):
            ta = c.t
            tb = cmds[k + 1].t if k + 1 < len(cmds) else t0 + duration
            ia = max(int(round((ta - t0) * fs)), 0)
            ib = min(int(round((tb - t0) * fs)), n)
            if ib > ia:
                pan[ia:ib] = c.pan
                ob_gain[ia:ib] = db_lin(c.obstacle_db)
            if c.mode in (GUIDE, SEARCH):
                if next_note is None:
                    next_note = ta
                note = self.search if c.mode == SEARCH else self.guide
                while next_note < tb:
                    self._add(notes, int(round((next_note - t0) * fs)), note * db_lin(c.gain_db))
                    next_note += max(c.interval_s, 0.2)
                if k + 1 < len(cmds) and cmds[k + 1].mode != c.mode:
                    next_note = None  # passage recherche ↔ chemin : nouveau rythme immédiatement
            else:
                next_note = None
            if c.event == "arrived":
                self._add(center, int(round((ta - t0) * fs)), self.sounds["arrived"].mean(axis=1))
        speech, duck = self._speech(cmds, t0, n)
        if duck is not None:
            notes *= _smooth(duck, fs, 0.03)
        center += speech
        # pan et volume lissés : aucun clic aux changements
        gl, gr = equal_power(_smooth(pan, fs, self.tau))
        st = np.stack([notes * gl, notes * gr], axis=1)
        st += center[:, None]  # centré, mono sur les deux oreilles (comme Web Audio)
        g = _smooth(ob_gain, fs, self.tau_ob)
        if g.max() > 1e-6:
            reps = int(math.ceil(n / len(self.obstacle)))
            st += np.tile(self.obstacle, (reps, 1))[:n] * g[:, None]
        st *= self.master
        peak = float(np.abs(st).max())
        if peak > 0.98:
            log.warning("Piste trop forte (crête %.2f) : ramenée à 0,98", peak)
            st *= 0.98 / peak
        return st.astype(np.float32)

    def _speech(self, cmds: list[SoundCommand], t0: float, n: int):
        """Piste des phrases (mono) et gain de la couche chemin (0 pendant une phrase « duck »)."""
        fs = self.fs
        out = np.zeros(n)
        self.speeches = []
        seen: set[int] = set()
        items = []
        for c in cmds:
            sid = int(getattr(c, "speech_id", 0) or 0)
            if sid and sid not in seen and getattr(c, "speech", ""):
                seen.add(sid)
                items.append((c.t, c.speech, bool(getattr(c, "speech_duck", False))))
        if not items:
            return out, None
        output = str(getattr(self.tts, "output", "auto")) if self.tts is not None else "auto"
        if output == "off":
            return out, None
        from visionaid.audio import tts

        kw = tts.voice_kwargs(self.tts)
        cache = Path(self.tts_cache) if self.tts_cache is not None else None
        duck = np.ones(n)
        t_free = -math.inf
        for t, text, dk in items:
            x = tts.synth(text, fs, cache_dir=cache, **kw)
            dur = len(x) / fs if x is not None else 0.08 * len(text)
            start = max(t, t_free)  # phrases à la suite, jamais superposées
            t_free = start + dur + 0.3
            self.speeches.append((start, start + dur, text))
            i = int(round((start - t0) * fs))
            if x is not None:
                self._add(out, i, x)
            if dk:
                duck[max(i, 0) : max(min(i + int((dur + 0.3) * fs), n), 0)] = 0.0
        return out, duck

    def write_wav(self, path: str | Path, stereo: np.ndarray) -> None:
        import soundfile as sf

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), stereo, self.fs, subtype="PCM_16")
