"""Reconnaissance vocale sur le PC (Whisper, `transformers`) des demandes enregistrées par le
téléphone (« je cherche ma gourde »).

Le téléphone enregistre quelques secondes (MediaRecorder : audio/mp4 sur iPhone, audio/webm
ailleurs) et envoie le fichier ; ffmpeg le décode (via `transformers`). Le modèle est chargé en
arrière-plan au démarrage du direct (téléchargé une seule fois, ~1 Go pour whisper-small).
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

from visionaid.utils.logging import get_logger

log = get_logger("stt")

SUFFIX = {
    "mp4": ".m4a",
    "aac": ".m4a",
    "m4a": ".m4a",
    "webm": ".webm",
    "ogg": ".ogg",
    "wav": ".wav",
}


class WhisperSTT:
    """Transcription de courtes phrases, modèle chargé une fois (fil d'arrière-plan)."""

    def __init__(self, model: str = "openai/whisper-small", language: str = "fr") -> None:
        self.model_name = model
        self.language = {"fr": "french", "en": "english"}.get(language, language)
        self.pipe = None
        self.error: str | None = None
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self.times: list[float] = []

    def preload(self) -> WhisperSTT:
        threading.Thread(target=self._load, name="whisper-load", daemon=True).start()
        return self

    def _load(self) -> None:
        try:
            import torch
            from transformers import pipeline

            dev = "mps" if torch.backends.mps.is_available() else "cpu"
            t0 = time.time()
            self.pipe = pipeline("automatic-speech-recognition", model=self.model_name, device=dev)
            log.info("Whisper prêt (%s sur %s, %.0f s)", self.model_name, dev, time.time() - t0)
        except Exception as e:  # noqa: BLE001 - modèle absent, pas de réseau…
            self.error = repr(e)[:300]
            log.error("Whisper indisponible : %s", self.error)
        finally:
            self._ready.set()

    def transcribe(self, audio: bytes, mime: str = "audio/mp4", timeout: float = 180.0) -> str:
        """Fichier audio (octets) → texte ; chaîne vide si échec."""
        if self.pipe is None and not self._ready.is_set():
            if not any(t.name == "whisper-load" for t in threading.enumerate()):
                self.preload()
            self._ready.wait(timeout)
        if self.pipe is None:
            return ""
        sub = (mime or "").split("/")[-1].split(";")[0].strip().lower()
        suffix = SUFFIX.get(sub, ".m4a")
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / f"demande{suffix}"
            f.write_bytes(audio)
            t0 = time.time()
            try:
                with self._lock:
                    r = self.pipe(
                        str(f), generate_kwargs={"language": self.language, "task": "transcribe"}
                    )
            except Exception as e:  # noqa: BLE001 - fichier illisible
                log.warning("Transcription impossible : %s", e)
                return ""
            self.times.append(time.time() - t0)
        return str(r.get("text", "")).strip()
