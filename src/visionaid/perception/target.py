"""Prompt fixe → fiche cible (`config/targets/<nom>.yaml`), sans modèle de langage.

La phrase est normalisée (minuscules, accents, ponctuation, mots vides) puis comparée aux phrases
déclenchantes de chaque fiche : égalité exacte d'abord, puis inclusion du nom de l'objet. La fiche
retenue surcharge la config (prompts de détection, photos de référence, modèle de couleur, seuil).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from visionaid.utils.config import _deep_update, resolve_path

STOPWORDS = {
    "ou", "est", "sont", "ma", "mon", "mes", "la", "le", "les", "l", "trouve", "trouver",
    "cherche", "chercher", "moi", "je", "veux", "s", "il", "te", "plait", "stp", "svp", "d",
    "de", "du", "des", "un", "une", "a",
}  # fmt: skip


class UnknownTarget(ValueError):
    """Aucune fiche ne correspond à la phrase."""


@dataclass
class TargetSheet:
    """Fiche cible chargée depuis YAML."""

    name: str
    label: str
    phrases: list[str]
    overrides: dict
    path: Path
    keys: set[str] = field(default_factory=set)


def normalize(text: str) -> str:
    """Minuscules, sans accents ni ponctuation, espaces simples."""
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split())


def content_words(text: str) -> tuple[str, ...]:
    """Mots porteurs de sens (sans mots vides), au singulier approximatif."""
    out = []
    for w in normalize(text).split():
        if w in STOPWORDS:
            continue
        if len(w) > 3 and w.endswith(("s", "x")):
            w = w[:-1]
        out.append(w)
    return tuple(out)


def load_sheets(directory: str | Path | None = None) -> list[TargetSheet]:
    """Toutes les fiches du dossier, triées par nom."""
    d = resolve_path(directory or "config/targets")
    sheets = []
    for p in sorted(Path(d).glob("*.yaml")):
        y = yaml.safe_load(p.read_text()) or {}
        name = str(y.get("name") or p.stem)
        phrases = [str(x) for x in y.get("phrases", [])] + [name]
        keys = {" ".join(content_words(x)) for x in phrases}
        keys.discard("")
        sheets.append(
            TargetSheet(name, str(y.get("label", name)), phrases, y.get("overrides", {}), p, keys)
        )
    return sheets


def resolve_target(query: str, directory: str | Path | None = None) -> TargetSheet:
    """Fiche correspondant à la phrase ; `UnknownTarget` (avec la liste des cibles) sinon."""
    sheets = load_sheets(directory)
    key = " ".join(content_words(query))
    if key:
        exact = [s for s in sheets if key in s.keys]
        if len(exact) == 1:
            return exact[0]
        words = set(key.split())
        partial = [s for s in sheets if any(set(k.split()) <= words for k in s.keys)]
        if len(partial) == 1:
            return partial[0]
    known = ", ".join(f"« {s.label} »" for s in sheets) or "aucune"
    raise UnknownTarget(f"cible inconnue pour « {query} ». Cibles disponibles : {known}.")


def apply_target(raw: dict, query: str | None) -> dict:
    """Applique la fiche correspondant à `query` (ou `raw['target']['query']`) à une config brute."""
    q = query if query is not None else (raw.get("target") or {}).get("query")
    if not q:
        return raw
    sheet = resolve_target(q, (raw.get("target") or {}).get("sheets_dir"))
    _deep_update(raw, yaml.safe_load(yaml.safe_dump(sheet.overrides)) or {})
    raw.setdefault("target", {})
    raw["target"]["query"] = q
    raw["target"]["name"] = sheet.name
    raw["target"]["label"] = sheet.label
    return raw


def load_config_for_target(query: str | None, path=None, overrides: dict | None = None):
    """Config avec la fiche cible appliquée (les `overrides` explicites priment sur la fiche)."""
    from visionaid.utils.config import load_config

    ov = dict(overrides or {})
    ov["target.query"] = query
    return load_config(path, ov)
