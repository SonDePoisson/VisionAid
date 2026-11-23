"""Préparation du premier lancement : téléchargement et chargement des modèles, une seule fois.

Les modèles sont chargés par les mêmes fonctions que le guidage (ainsi rien n'est oublié) dans
un processus séparé ; la progression affichée est le volume réellement téléchargé dans les
caches. Une fois tout prêt, un marqueur `.cache/app/prepared.json` évite de recommencer.
Si la connexion coupe, les caches gardent ce qui est déjà là : la reprise repart de là.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any

from visionaid.utils.config import resolve_path
from visionaid.utils.logging import get_logger

log = get_logger("app.prepare")

STEPS: list[dict[str, str]] = [
    {"id": "objets", "label": "Reconnaissance des objets"},
    {"id": "distances", "label": "Mesure des distances"},
    {"id": "voix", "label": "Reconnaissance de la voix"},
]
# ordre de grandeur des téléchargements (affichage du temps restant seulement)
EXPECTED_BYTES = 2.6e9
MARKER = ".cache/app/prepared.json"
MARKER_VERSION = 1


def marker_path() -> Path:
    return resolve_path(MARKER)


def is_prepared() -> bool:
    try:
        return json.loads(marker_path().read_text()).get("version") == MARKER_VERSION
    except (OSError, ValueError):
        return False


def cache_dirs(raw: dict) -> list[Path]:
    """Dossiers où les bibliothèques écrivent les modèles téléchargés."""
    dirs = [resolve_path(raw["paths"]["cache"])]
    try:
        from huggingface_hub import constants

        dirs.append(Path(constants.HF_HUB_CACHE))
    except Exception:  # noqa: BLE001 - huggingface_hub absent : le cache local suffit
        pass
    try:
        import torch

        dirs.append(Path(torch.hub.get_dir()))
    except Exception:  # noqa: BLE001
        pass
    return dirs


def dir_bytes(dirs: list[Path]) -> int:
    total = 0
    for d in dirs:
        if not d.is_dir():
            continue
        for root, _sub, files in os.walk(d):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    return total


def _worker(raw: dict, out: Any) -> None:
    """Sous-processus : charge chaque modèle (télécharge ce qui manque)."""
    from visionaid.utils.config import _to_dataclass

    def step(sid: str, fn) -> bool:
        out.put(("start", sid, ""))
        try:
            fn()
        except Exception as e:  # noqa: BLE001 - pas de réseau, disque plein…
            out.put(("error", sid, repr(e)[:400]))
            return False
        out.put(("done", sid, ""))
        return True

    def objets() -> None:
        from visionaid.apps.live_blocks import LivePerceptionBlock

        LivePerceptionBlock(raw)

    def distances() -> None:
        from visionaid.perception.depth import DepthEstimator

        DepthEstimator(_to_dataclass("config", raw))

    def voix() -> None:
        from visionaid.phone.stt import WhisperSTT

        c = raw.get("command") or {}
        stt = WhisperSTT(str(c.get("whisper_model", "openai/whisper-small")))
        stt._load()
        if stt.pipe is None:
            raise RuntimeError(stt.error or "modèle de la voix indisponible")

    for sid, fn in (("objets", objets), ("distances", distances), ("voix", voix)):
        if not step(sid, fn):
            out.put(("end", "", "error"))
            return
    out.put(("end", "", "ok"))


class Preparer:
    """Lance la préparation et en expose l'état (lu par l'interface)."""

    def __init__(self, raw: dict) -> None:
        self.raw = raw
        self._lock = threading.Lock()
        self.status = "idle"  # idle | running | done | error
        self.steps = {s["id"]: "pending" for s in STEPS}
        self.error = ""
        self.bytes0 = 0
        self.bytes = 0
        self.t0 = 0.0
        self.on_done = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self.status == "running":
                return
            self.status = "running"
            self.error = ""
            self.steps = {s["id"]: "pending" for s in STEPS}
        self._thread = threading.Thread(target=self._run, name="prepare", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        dirs = cache_dirs(self.raw)
        self.bytes0 = self.bytes = dir_bytes(dirs)
        self.t0 = time.time()
        ctx = mp.get_context("spawn")
        q = ctx.Queue()
        p = ctx.Process(target=_worker, args=(self.raw, q), name="prepare-models", daemon=True)
        p.start()
        result = "error"
        last_scan = 0.0
        while True:
            try:
                kind, sid, msg = q.get(timeout=0.5)
            except queue.Empty:
                kind = None
            if time.time() - last_scan > 1.0:
                self.bytes = dir_bytes(dirs)
                last_scan = time.time()
            if kind in ("start", "done", "error"):
                with self._lock:
                    self.steps[sid] = {"start": "running", "done": "done", "error": "error"}[kind]
                    if kind == "error":
                        self.error = msg
                        log.error("Préparation « %s » : %s", sid, msg)
            elif kind == "end":
                result = msg
                break
            if kind is None and not p.is_alive():
                with self._lock:
                    self.error = self.error or "la préparation s'est arrêtée"
                break
        p.join(5)
        self.bytes = dir_bytes(dirs)
        if result == "ok":
            path = marker_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"version": MARKER_VERSION, "t": time.time()}))
        with self._lock:
            self.status = "done" if result == "ok" else "error"
        if result == "ok" and self.on_done is not None:
            self.on_done()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            got = max(0, self.bytes - self.bytes0)
            n_done = sum(1 for v in self.steps.values() if v == "done")
            frac_steps = n_done / len(STEPS)
            frac_bytes = min(1.0, got / EXPECTED_BYTES)
            pct = 100 if self.status == "done" else int(min(99, 100 * max(frac_steps, frac_bytes)))
            elapsed = time.time() - self.t0 if self.t0 else 0.0
            remaining = None
            if self.status == "running" and pct > 3 and elapsed > 5:
                remaining = int(elapsed * (100 - pct) / pct / 60) + 1
            return {
                "status": self.status,
                "percent": pct,
                "minutes_left": remaining,
                "downloaded_gb": round(got / 1e9, 2),
                "steps": [
                    {"id": s["id"], "label": s["label"], "state": self.steps[s["id"]]}
                    for s in STEPS
                ],
                "error": self.error,
            }
