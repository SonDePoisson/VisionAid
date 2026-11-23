"""Réglages de l'application, gardés d'un lancement à l'autre (JSON dans le dossier de cache)."""

from __future__ import annotations

import json
import math
import threading
from pathlib import Path
from typing import Any

from visionaid.utils.config import resolve_path

# Volumes affichés en % ; la valeur par défaut de chaque son correspond à son niveau d'origine
# (0 dB), si bien que « Rétablir les réglages d'origine » ne change rien au rendu de référence.
VOLUME_DEFAULTS: dict[str, int] = {
    "general": 80,
    "chemin": 70,
    "obstacles": 60,
    "recherche": 50,
    "arrivee": 70,
    "voix": 80,
}

DEFAULTS: dict[str, Any] = {
    "setup_done": False,  # mise en route (téléphone + casque) déjà faite une fois
    "mode": "voice",  # voice : la personne dit ce qu'elle cherche | here : choisi sur l'ordinateur
    "object": "gourde",  # objet choisi sur l'ordinateur (mode here)
    "volumes": dict(VOLUME_DEFAULTS),
    "advanced": False,
    "viz": False,  # vue 3D (Rerun) pendant le guidage — prend effet au prochain lancement
    "record": False,  # enregistrement des sessions — prend effet au prochain lancement
    "headset_tested": "",  # date (AAAA-MM-JJ) du dernier test du casque réussi
}

OBJECTS: dict[str, dict[str, Any]] = {
    "gourde": {
        "label": "Ma gourde",
        "phrase": "je cherche ma gourde",
        "spoken": "la gourde",
        "plural": False,
        "feminine": True,
    },
    "cles": {
        "label": "Mes clés",
        "phrase": "où sont mes clés",
        "spoken": "les clés",
        "plural": True,
        "feminine": True,
    },
}


def volume_db(key: str, pct: float) -> float:
    """% affiché → gain en dB relatif au niveau d'origine du son (0 % = muet)."""
    ref = VOLUME_DEFAULTS.get(key, 70)
    if pct <= 0:
        return -120.0
    return round(20.0 * math.log10(float(pct) / ref), 2)


def levels_db(volumes: dict[str, float]) -> dict[str, float]:
    return {k: volume_db(k, volumes.get(k, VOLUME_DEFAULTS[k])) for k in VOLUME_DEFAULTS}


class Settings:
    """Réglages persistants ; lecture/écriture protégées (appelés depuis plusieurs threads)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or resolve_path(".cache/app/settings.json")
        self._lock = threading.Lock()
        self.data: dict[str, Any] = json.loads(json.dumps(DEFAULTS))
        try:
            saved = json.loads(self.path.read_text())
            if isinstance(saved, dict):
                vols = dict(VOLUME_DEFAULTS)
                vols.update({k: v for k, v in (saved.get("volumes") or {}).items() if k in vols})
                self.data.update({k: v for k, v in saved.items() if k in DEFAULTS})
                self.data["volumes"] = vols
        except (OSError, ValueError):
            pass

    def get(self, key: str) -> Any:
        with self._lock:
            return json.loads(json.dumps(self.data[key]))

    def update(self, **kw: Any) -> dict[str, Any]:
        with self._lock:
            for k, v in kw.items():
                if k not in DEFAULTS:
                    raise KeyError(k)
                if k == "volumes":
                    vols = dict(self.data["volumes"])
                    for name, pct in (v or {}).items():
                        if name in VOLUME_DEFAULTS:
                            vols[name] = int(max(0, min(100, round(float(pct)))))
                    v = vols
                if k == "mode" and v not in ("voice", "here"):
                    raise ValueError(v)
                if k == "object" and v not in OBJECTS:
                    raise ValueError(v)
                self.data[k] = v
            snapshot = json.loads(json.dumps(self.data))
        self._save(snapshot)
        return snapshot

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self.data))

    def _save(self, data: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            tmp.replace(self.path)
        except OSError:
            pass  # réglages non gardés : l'application continue
