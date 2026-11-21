"""Agrégation des métriques dans outputs/report.json (fusion par section)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from visionaid.utils.config import ROOT


def report_path() -> Path:
    return ROOT / "outputs" / "report.json"


def _clean(o: Any) -> Any:
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def update_report(section: str, data: dict) -> dict:
    """Fusionne `data` dans la section `section` du rapport."""
    p = report_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    rep = json.loads(p.read_text()) if p.exists() else {}
    rep.setdefault(section, {}).update(_clean(data))
    p.write_text(json.dumps(rep, indent=2, ensure_ascii=False))
    return rep


def file_hash(path: str | Path, extra: str = "") -> str:
    """Empreinte courte d'un fichier (taille + premiers/derniers Mo) et d'une chaîne de config."""
    p = Path(path)
    h = hashlib.sha1()
    h.update(str(p.stat().st_size).encode())
    with open(p, "rb") as fh:
        h.update(fh.read(1 << 20))
        fh.seek(max(p.stat().st_size - (1 << 20), 0))
        h.update(fh.read(1 << 20))
    h.update(extra.encode())
    return h.hexdigest()[:12]
