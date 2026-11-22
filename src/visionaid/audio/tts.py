"""Synthèse vocale côté PC (macOS `say`) : rejeu de session et rendu hors ligne.

En direct, les phrases sont dites par le téléphone (Web Speech, `web/audio.js`), dans le casque.
Ici : `MacSpeaker` les dit sur le haut-parleur du Mac (rejeu d'une session sans téléphone) et
`synth` les rend en échantillons pour la piste WAV des vidéos.
"""

from __future__ import annotations

import hashlib
import queue
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

import numpy as np

from visionaid.utils.logging import get_logger

log = get_logger("tts")


def available() -> bool:
    return shutil.which("say") is not None


def synth(
    text: str, fs: int, voice: str = "Thomas", rate_wpm: int = 190, cache_dir: Path | None = None
) -> np.ndarray | None:
    """Phrase → échantillons mono float64 à `fs` (None si `say` est absent ou échoue)."""
    if not text or not available():
        return None
    import soundfile as sf

    key = hashlib.sha1(f"{voice}|{rate_wpm}|{fs}|{text}".encode()).hexdigest()[:16]
    cpath = Path(cache_dir) / f"{key}.wav" if cache_dir is not None else None
    if cpath is not None and cpath.exists():
        x, _ = sf.read(str(cpath), always_2d=True)
        return x.mean(axis=1)
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "s.aiff"
        try:
            subprocess.run(
                ["say", "-v", voice, "-r", str(int(rate_wpm)), "-o", str(out), text],
                check=True,
                timeout=60,
                capture_output=True,
            )
            x, sr = sf.read(str(out), always_2d=True)
        except Exception as e:  # noqa: BLE001 - voix absente, format non lu…
            log.warning("Synthèse vocale impossible (%s) : %s", voice, e)
            return None
    x = x.mean(axis=1)
    if sr != fs:
        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(int(sr), int(fs))
        x = resample_poly(x, fs // g, sr // g)
    peak = float(np.abs(x).max()) if len(x) else 0.0
    if peak > 0:
        x = x * (0.5 / peak)  # crête −6 dBFS, à peu près le niveau des sons du guidage
    if cpath is not None:
        cpath.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(cpath), x, fs, subtype="PCM_16")
    return x


class MacSpeaker:
    """Dit les phrases une à une sur le haut-parleur du Mac (fil d'exécution dédié)."""

    def __init__(self, voice: str = "Thomas", rate_wpm: int = 190) -> None:
        self.voice = voice
        self.rate = int(rate_wpm)
        self.q: queue.Queue = queue.Queue()
        self.ok = available()
        self.n = 0
        if self.ok:
            threading.Thread(target=self._run, name="mac-tts", daemon=True).start()
        else:
            log.warning("`say` absent : phrases affichées seulement")

    def say(self, text: str) -> None:
        log.info("Voix : %s", text)
        self.n += 1
        if self.ok:
            self.q.put(text)

    def _run(self) -> None:
        while True:
            text = self.q.get()
            if text is None:
                return
            try:
                subprocess.run(
                    ["say", "-v", self.voice, "-r", str(self.rate), text], timeout=60, check=False
                )
            except Exception as e:  # noqa: BLE001
                log.warning("say : %s", e)

    def close(self) -> None:
        self.q.put(None)
