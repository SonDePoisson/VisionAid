"""Synthèse vocale côté PC : Pocket TTS (Kyutai, voix neuronale française, sur le processeur),
avec macOS `say` en secours.

`synth` rend une phrase en échantillons : servie au téléphone (`/tts`, jouée dans le casque),
piste WAV des vidéos. `MacSpeaker` la dit sur le haut-parleur du Mac (rejeu sans téléphone).
"""

from __future__ import annotations

import hashlib
import queue
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

import numpy as np

from visionaid.utils.logging import get_logger

log = get_logger("tts")


def say_available() -> bool:
    return shutil.which("say") is not None


def pocket_available() -> bool:
    try:
        import pocket_tts  # noqa: F401
    except ImportError:
        return False
    return True


def available() -> bool:
    return pocket_available() or say_available()


def pocket_text(text: str) -> str:
    """Le modèle français n'a pas vu de guillemets ni de deux-points à l'entraînement : il les
    lit mal (« je n'ai pas compris « X » » devenait « je n'aime pas conclure »). On les
    remplace par des pauses."""
    t = text.replace("’", "'").replace("\u00a0", " ").replace("\u202f", " ")
    t = re.sub(r"\s*[«»“”\"]\s*", " , ", t)
    t = re.sub(r"\s*:\s*", ", ", t)
    t = re.sub(r"\s*,(\s*,)+", ",", t)  # virgules doublées
    t = re.sub(r"\s+,", ",", t)
    t = re.sub(r"([.!?]),", r"\1", t)
    t = re.sub(r",\s*([.!?])", r"\1", t)
    t = re.sub(r"^\s*,\s*|\s*,\s*$", "", t)
    return " ".join(t.split())


class _Pocket:
    """Modèle Pocket TTS chargé une fois par processus (~2 s) ; une phrase à la fois."""

    _lock = threading.Lock()
    _models: dict = {}

    @classmethod
    def get(cls, language: str, voice: str):
        with cls._lock:
            key = (language, voice)
            if key not in cls._models:
                from pocket_tts import TTSModel

                m = TTSModel.load_model(language=language)
                cls._models[key] = (m, m.get_state_for_audio_prompt(voice))
                log.info("Voix Pocket TTS prête (%s, %s)", language, voice)
            return cls._models[key]

    @classmethod
    def synth(cls, text: str, language: str, voice: str) -> tuple[np.ndarray, int]:
        text = pocket_text(text)
        m, state = cls.get(language, voice)
        with cls._lock:
            a = m.generate_audio(state, text)
        return np.asarray(a, dtype=np.float64).reshape(-1), int(m.sample_rate)


def warm(engine: str = "pocket", language: str = "french", voice: str = "estelle") -> None:
    """Charge la voix à l'avance (premier message dit sans attendre le chargement)."""
    if engine == "pocket" and pocket_available():
        try:
            _Pocket.get(language, voice)
        except Exception as e:  # noqa: BLE001 - poids absents hors ligne…
            log.warning("Pocket TTS indisponible (%s) : voix de macOS en secours", e)


def _speak_pocket(text: str, language: str, voice: str) -> tuple[np.ndarray, int] | None:
    try:
        return _Pocket.synth(text, language, voice)
    except Exception as e:  # noqa: BLE001
        log.warning("Pocket TTS impossible : %s", e)
        return None


def synth(
    text: str,
    fs: int,
    voice: str = "Thomas",
    rate_wpm: int = 190,
    cache_dir: Path | None = None,
    engine: str = "say",
    pocket_voice: str = "estelle",
    pocket_language: str = "french",
) -> np.ndarray | None:
    """Phrase → échantillons mono float64 à `fs` (None si aucune voix ne marche).

    `engine` : « pocket » (Pocket TTS, `say` en secours) ou « say » (`voice`, `rate_wpm`)."""
    if not text or not available():
        return None
    import soundfile as sf

    use_pocket = engine == "pocket" and pocket_available()
    tag = f"pocket|{pocket_language}|{pocket_voice}" if use_pocket else f"{voice}|{rate_wpm}"
    key = hashlib.sha1(f"{tag}|{fs}|{text}".encode()).hexdigest()[:16]
    cpath = Path(cache_dir) / f"{key}.wav" if cache_dir is not None else None
    if cpath is not None and cpath.exists():
        x, _ = sf.read(str(cpath), always_2d=True)
        return x.mean(axis=1)
    out = _speak_pocket(text, pocket_language, pocket_voice) if use_pocket else None
    if out is None:
        if not say_available():
            return None
        out = _speak_say(text, voice, rate_wpm)
        if out is None:
            return None
        cpath = None  # secours : on ne garde pas cette voix en cache
    x, sr = out
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


def _speak_say(text: str, voice: str, rate_wpm: int) -> tuple[np.ndarray, int] | None:
    import soundfile as sf

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
    return x.mean(axis=1), int(sr)


def voice_kwargs(tcfg) -> dict:
    """Réglages de voix de la section `tts` de la config, pour `synth` et `MacSpeaker`."""
    g = (lambda k, d: getattr(tcfg, k, d)) if tcfg is not None else (lambda k, d: d)
    return {
        "engine": str(g("engine", "pocket")),
        "pocket_voice": str(g("pocket_voice", "estelle")),
        "pocket_language": str(g("pocket_language", "french")),
        "voice": str(g("mac_voice", "Thomas")),
        "rate_wpm": int(g("mac_rate_wpm", 190)),
    }


class MacSpeaker:
    """Dit les phrases une à une sur le haut-parleur du Mac (fil d'exécution dédié)."""

    def __init__(self, voice: str = "Thomas", rate_wpm: int = 190, **kw) -> None:
        self.kw = {"voice": voice, "rate_wpm": int(rate_wpm), **kw}
        self.q: queue.Queue = queue.Queue()
        self.ok = available() and shutil.which("afplay") is not None
        self.n = 0
        if self.ok:
            threading.Thread(target=self._run, name="mac-tts", daemon=True).start()
        else:
            log.warning("Pas de voix sur cet ordinateur : phrases affichées seulement")

    def say(self, text: str) -> None:
        log.info("Voix : %s", text)
        self.n += 1
        if self.ok:
            self.q.put(text)

    def _run(self) -> None:
        import soundfile as sf

        warm(
            self.kw.get("engine", "say"),
            self.kw.get("pocket_language", "french"),
            self.kw.get("pocket_voice", "estelle"),
        )
        while True:
            text = self.q.get()
            if text is None:
                return
            try:
                x = synth(text, 24000, **self.kw)
                if x is None:
                    continue
                with tempfile.TemporaryDirectory() as d:
                    f = Path(d) / "s.wav"
                    sf.write(str(f), x, 24000, subtype="PCM_16")
                    subprocess.run(["afplay", str(f)], timeout=60, check=False)
            except Exception as e:  # noqa: BLE001
                log.warning("Voix du Mac : %s", e)

    def close(self) -> None:
        self.q.put(None)
