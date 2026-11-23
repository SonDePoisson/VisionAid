"""Chargement de la configuration YAML en dataclasses (immuables par section)."""

from __future__ import annotations

import copy
import dataclasses
import os
import sys
from pathlib import Path
from typing import Any

import yaml

_PKG = Path(__file__).resolve().parents[1]  # dossier du paquet `visionaid`
_REPO = _PKG.parents[1]  # racine du dépôt quand le paquet est lancé depuis les sources


def _is_source_checkout() -> bool:
    """Lancé depuis un clone du dépôt (`uv run …`) plutôt qu'installé comme logiciel."""
    return (_REPO / "pyproject.toml").is_file() and (_REPO / "config" / "default.yaml").is_file()


def user_dir() -> Path:
    """Dossier des fichiers de l'utilisateur (sorties, cache, certificats, sessions, réglages).

    `VISIONAID_HOME` le remplace ; sinon l'emplacement habituel du système.
    """
    env = os.environ.get("VISIONAID_HOME")
    if env:
        return Path(env).expanduser()
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "VisionAId"
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming") / "VisionAId"
    return Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "visionaid"


SOURCE_CHECKOUT = _is_source_checkout()
# Ressources en lecture seule (config, sons) : le dépôt, ou les données livrées dans le paquet.
RESOURCES = _REPO if SOURCE_CHECKOUT else _PKG / "_data"
# Fichiers écrits : le dépôt (comportement historique), ou le dossier de l'utilisateur.
ROOT = _REPO if SOURCE_CHECKOUT else user_dir()
DEFAULT_CONFIG = RESOURCES / "config" / "default.yaml"
_RESOURCE_PREFIXES = ("config", "assets")


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
    _apply_overrides(raw, overrides)
    query = (raw.get("target") or {}).get("query")
    if query:  # prompt fixe : la fiche cible surcharge la config, les surcharges explicites priment
        from visionaid.perception.target import apply_target

        apply_target(raw, query)
        _apply_overrides(raw, {k: v for k, v in (overrides or {}).items() if k != "target.query"})
    return raw


def _apply_overrides(raw: dict, overrides: dict | None) -> None:
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


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> Any:
    """Charge la configuration et la retourne sous forme de dataclasses imbriquées."""
    return _to_dataclass("config", load_raw(path, overrides))


def resolve_path(p: str | Path) -> Path:
    """Chemin relatif à la racine du projet.

    Installé comme logiciel : `config/…` et `assets/…` viennent du paquet (lecture seule), le
    reste (sorties, cache, sessions, certificats) va dans le dossier de l'utilisateur.
    """
    p = Path(p)
    if p.is_absolute():
        return p
    if p.parts and p.parts[0] in _RESOURCE_PREFIXES:
        return RESOURCES / p
    return ROOT / p


def length_to_m(value, name: str = "longueur") -> float | None:
    """Longueur saisie par l'utilisateur → mètres. Accepte m, cm ou mm sans unité explicite :
    > 3 est lu en cm (« 150 » → 1,50 m), > 300 en mm. Les hauteurs humaines ne laissent pas
    d'ambiguïté."""
    if value is None:
        return None
    v = float(value)
    if v > 300:
        out = v / 1000.0
    elif v > 3:
        out = v / 100.0
    else:
        out = v
    if out != v:
        import logging

        logging.getLogger("visionaid.config").warning(
            "%s = %g interprétée comme %g m (unité déduite)", name, v, out
        )
    return out
