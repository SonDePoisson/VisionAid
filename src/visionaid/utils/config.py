"""Chargement de la configuration YAML en dataclasses (immuables par section)."""

from __future__ import annotations

import copy
import dataclasses
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = ROOT / "config" / "default.yaml"


def _to_dataclass(name: str, data: Any) -> Any:
    """Convertit récursivement un dict en instance de dataclass générée."""
    if not isinstance(data, dict):
        return data
    fields = []
    values = {}
    for key, val in data.items():
        conv = _to_dataclass(f"{name}_{key}", val)
        fields.append((str(key), type(conv), dataclasses.field(default=None)))
        values[str(key)] = conv
    cls = dataclasses.make_dataclass(name.title().replace("_", ""), fields, frozen=False)
    return cls(**values)


def to_dict(cfg: Any) -> Any:
    """Inverse de `_to_dataclass`."""
    if dataclasses.is_dataclass(cfg):
        return {f.name: to_dict(getattr(cfg, f.name)) for f in dataclasses.fields(cfg)}
    return copy.deepcopy(cfg)


def _deep_update(base: dict, upd: dict) -> dict:
    for k, v in upd.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def load_raw(path: str | Path | None = None, overrides: dict | None = None) -> dict:
    """Charge le YAML brut, applique les surcharges (dict imbriqué ou clés pointées)."""
    with open(path or DEFAULT_CONFIG) as fh:
        raw = yaml.safe_load(fh) or {}
    for key, val in (overrides or {}).items():
        if "." in key:
            node = raw
            parts = key.split(".")
            for p in parts[:-1]:
                node = node.setdefault(p, {})
            node[parts[-1]] = val
        elif isinstance(val, dict) and isinstance(raw.get(key), dict):
            _deep_update(raw[key], val)
        else:
            raw[key] = val
    return raw


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> Any:
    """Charge la configuration et la retourne sous forme de dataclasses imbriquées."""
    return _to_dataclass("config", load_raw(path, overrides))


def resolve_path(p: str | Path) -> Path:
    """Chemin relatif à la racine du projet."""
    p = Path(p)
    return p if p.is_absolute() else ROOT / p
