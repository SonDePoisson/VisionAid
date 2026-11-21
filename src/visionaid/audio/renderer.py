"""Rendu sonore des consignes : balise spatialisée, alertes, jingle d'arrivée ; WAV ou temps réel."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from numba import njit

from visionaid.audio.binaural import smooth_azimuth, spatialize
from visionaid.bus.messages import GuidanceCue
from visionaid.utils.logging import get_logger

log = get_logger("audio")

MODE_SILENT, MODE_BEACON, MODE_ALERT, MODE_STOP = 0, 1, 2, 3
STATE_MODE = {
    "SEARCHING": MODE_BEACON,
    "NAVIGATING": MODE_BEACON,
    "APPROACHING": MODE_BEACON,
    "ARRIVED": MODE_SILENT,
    "OBSTACLE_ALERT": MODE_ALERT,
    "TRACKING_LOST": MODE_STOP,
}


@njit(cache=True)
def _source_kernel(mode, freq, rate, gain, fs, beep_s, alert_freq):
    """Synthèse mono à phase continue. Bips à enveloppe en cosinus surélevé (pas de clic)."""
    n = mode.shape[0]
    out = np.zeros(n)
    ph = 0.0  # phase porteuse
    bph = 0.0  # phase du train de bips (0..1)
    aph = 0.0  # phase de modulation de l'alerte
    stop_ph = 0.0
    for i in range(n):
        m = mode[i]
        if m == 1:
            bph += rate[i] / fs
            if bph >= 1.0:
                bph -= 1.0
            tb = bph / rate[i] if rate[i] > 0 else 1e9
            env = 0.0
            if tb < beep_s:
                env = 0.5 - 0.5 * math.cos(2 * math.pi * tb / beep_s)
            ph += 2 * math.pi * freq[i] / fs
            out[i] = gain[i] * env * (math.sin(ph) + 0.3 * math.sin(2 * ph))
        elif m == 2:
            # alerte : deux tons alternés à 8 Hz, timbre riche (harmoniques impaires)
            aph += 8.0 / fs
            if aph >= 1.0:
                aph -= 1.0
            f = alert_freq if aph < 0.5 else alert_freq * 1.5
            ph += 2 * math.pi * f / fs
            env = 0.5 - 0.5 * math.cos(2 * math.pi * aph * 2.0)
            out[i] = (
                gain[i]
                * (0.4 + 0.6 * env)
                * (math.sin(ph) + 0.33 * math.sin(3 * ph) + 0.2 * math.sin(5 * ph))
            )
        elif m == 3:
            # repérage perdu : silence, un bip grave de 0,25 s toutes les 1,5 s
            stop_ph += 1.0 / fs
            if stop_ph >= 1.5:
                stop_ph -= 1.5
            env = 0.0
            if stop_ph < 0.25:
                env = 0.5 - 0.5 * math.cos(2 * math.pi * stop_ph / 0.25)
            ph += 2 * math.pi * 220.0 / fs
            out[i] = gain[i] * env * math.sin(ph)
        else:
            out[i] = 0.0
    return out


def jingle(fs: int, gain: float) -> np.ndarray:
    """Arpège ascendant do-mi-sol-do (0,6 s)."""
    notes = [523.25, 659.25, 783.99, 1046.5]
    d = 0.15
    t = np.arange(int(d * fs)) / fs
    env = np.sin(np.pi * t / d) ** 2
    return np.concatenate([gain * env * np.sin(2 * np.pi * f * t) for f in notes])


class AudioRenderer:
    """Convertit une suite de consignes horodatées en piste stéréo synchronisée."""

    def __init__(self, cfg_audio) -> None:
        a = cfg_audio
        self.fs = int(a.sample_rate)
        self.head_radius = float(a.head_radius_m)
        self.c = float(a.speed_of_sound)
        self.f0 = float(a.beacon_freq_hz)
        self.beep_s = float(a.beep_ms) / 1000.0
        self.rate_far = float(a.beep_rate_far_hz)
        self.rate_near = float(a.beep_rate_near_hz)
        self.far_m = float(a.beep_far_m)
        self.pitch_per_rad = float(a.pitch_per_rad)
        self.alert_f = float(a.alert_freq_hz)
        self.gain = float(a.gain)
        self.tau = float(a.smoothing_s)

    def beep_rate(self, distance: float) -> float:
        """Cadence des bips : plus rapide en s'approchant."""
        if not math.isfinite(distance):
            return self.rate_far
        x = float(np.clip(distance / self.far_m, 0.0, 1.0))
        return self.rate_near + (self.rate_far - self.rate_near) * x

    def controls(self, cues: list[GuidanceCue], t0: float, duration: float):
        """Signaux de contrôle par échantillon (bloqueur d'ordre 0 entre deux consignes)."""
        n = int(round(duration * self.fs))
        mode = np.zeros(n, np.int64)
        freq = np.full(n, self.f0)
        rate = np.full(n, self.rate_far)
        gain = np.zeros(n)
        az = np.zeros(n)
        jingles = []
        prev_state = None
        cues = sorted(cues, key=lambda c: c.t)
        for k, c in enumerate(cues):
            a = int(round((c.t - t0) * self.fs))
            b = int(round((cues[k + 1].t - t0) * self.fs)) if k + 1 < len(cues) else n
            a, b = max(a, 0), min(b, n)
            if c.state == "ARRIVED" and prev_state != "ARRIVED":
                jingles.append(a)
            prev_state = c.state
            if b <= a:
                continue
            m = STATE_MODE.get(c.state, MODE_SILENT)
            mode[a:b] = m
            az[a:b] = c.azimuth
            if m == MODE_BEACON:
                rate[a:b] = 0.7 if c.state == "SEARCHING" else self.beep_rate(c.distance)
                f = (
                    self.f0 * (1.0 + self.pitch_per_rad * c.elevation)
                    if c.state == "APPROACHING"
                    else self.f0
                )
                freq[a:b] = max(f, 100.0)
                gain[a:b] = self.gain * (0.5 if c.state == "SEARCHING" else 1.0)
            elif m == MODE_ALERT:
                gain[a:b] = self.gain * (0.6 + 0.4 * c.alert_level)
            elif m == MODE_STOP:
                gain[a:b] = self.gain * 0.8
                az[a:b] = 0.0
        return mode, freq, rate, gain, az, jingles

    def render(self, cues: list[GuidanceCue], t0: float, duration: float) -> np.ndarray:
        """Piste stéréo float32 (N,2) de durée `duration` commençant à `t0`."""
        mode, freq, rate, gain, az, jingles = self.controls(cues, t0, duration)
        # lissage des gains (évite les clics aux changements d'état)
        if self.tau > 0 and len(gain):
            from scipy.signal import lfilter

            k = math.exp(-1.0 / (0.01 * self.fs))
            gain = lfilter([1 - k], [1, -k], gain)
        mono = _source_kernel(mode, freq, rate, gain, float(self.fs), self.beep_s, self.alert_f)
        azs = smooth_azimuth(az, self.fs, self.tau)
        st = spatialize(mono, azs, self.fs, self.head_radius, self.c)
        jg = jingle(self.fs, self.gain)
        for a in jingles:
            b = min(a + len(jg), len(st))
            st[a:b] += jg[: b - a, None] * 0.7
        peak = float(np.abs(st).max()) if len(st) else 0.0
        if peak > 0.98:
            st *= 0.98 / peak
        return st.astype(np.float32)

    def write_wav(self, path: str | Path, stereo: np.ndarray) -> None:
        import soundfile as sf

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), stereo, self.fs, subtype="PCM_16")


class RealtimePlayer:
    """Lecture temps réel optionnelle via `sounddevice` (désactivée par défaut et dans les tests)."""

    def __init__(self, renderer: AudioRenderer, enabled: bool = False) -> None:
        self.r = renderer
        self.enabled = enabled
        self.sd = None
        if enabled:
            try:
                import sounddevice as sd  # type: ignore

                self.sd = sd
            except ImportError:
                log.warning("sounddevice absent : lecture temps réel désactivée")
                self.enabled = False

    def play_block(self, cue: GuidanceCue, block_s: float = 0.05) -> None:
        if not self.enabled or self.sd is None:
            return
        st = self.r.render([cue], cue.t, block_s)
        self.sd.play(st, self.r.fs, blocking=False)
