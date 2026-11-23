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
    spoken: str = ""  # nom prononcé dans les annonces (« la gourde »)
    plural: bool = False
    feminine: bool = False  # accord des textes de l'application (« trouvée »)


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


def spoken_from_label(label: str) -> str:
    """« ma gourde » → « la gourde », « mes clés » → « les clés » (nom prononcé par défaut)."""
    w = label.strip().split(" ", 1)
    art = {"ma": "la", "mon": "le", "mes": "les", "ta": "la", "ton": "le", "tes": "les"}
    if len(w) == 2 and w[0].lower() in art:
        return f"{art[w[0].lower()]} {w[1]}"
    return label


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
        label = str(y.get("label", name))
        spoken = str(y.get("spoken") or spoken_from_label(label))
        sheets.append(
            TargetSheet(
                name,
                label,
                phrases,
                y.get("overrides", {}),
                p,
                keys,
                spoken,
                bool(y.get("plural", False)),
                bool(y.get("feminine", spoken.startswith("la "))),
            )
        )
    return sheets


# ------------------------------------------------------------------ objets courants
VOCABULARY = "config/objects.yaml"


def _label_from_spoken(spoken: str) -> str:
    """« la télécommande » → « ma télécommande », « l'écharpe » → « mon écharpe »."""
    for art, pos in (("les ", "mes "), ("la ", "ma "), ("le ", "mon "), ("l'", "mon ")):
        if spoken.startswith(art):
            return pos + spoken[len(art) :]
    return spoken


def load_vocabulary(path: str | Path | None = None) -> list[TargetSheet]:
    """Objets courants (config/objects.yaml) sous forme de fiches « texte seul »."""
    p = resolve_path(path or VOCABULARY)
    if not Path(p).exists():
        return []
    out = []
    for name, y in (yaml.safe_load(Path(p).read_text()) or {}).items():
        spoken = str(y["dit"])
        plural = spoken.startswith("les ")
        fem = bool(y.get("fem", spoken.startswith("la ")))
        phrases = [spoken] + [str(m) for m in y.get("mots", [])]
        keys = {" ".join(content_words(x)) for x in phrases}
        keys.discard("")
        overrides = {
            "target": {"name": str(name), "height_m": None},
            "detector": {
                "text_prompts": [str(e) for e in y["en"]],
                "negative_prompts": [],
            },
            # photos data/ref/<nom>_*.jpg si on en dépose ; sinon reconnu par le texte seul
            "paths": {"ref_glob": f"{name}_*.jpg"},
            "reid": {
                "color_model": "none",
                "w_embed": 1.0,
                "w_color": 0.0,
                "threshold_file": f"config/reid_threshold_{name}.yaml",
                "textonly_conf": float(y.get("conf", 0.30)),
            },
        }
        out.append(
            TargetSheet(
                str(name),
                _label_from_spoken(spoken),
                phrases,
                overrides,
                Path(p),
                keys,
                spoken,
                plural,
                fem,
            )
        )
    return out


def _find_in(words: tuple[str, ...], key: tuple[str, ...]) -> int:
    """Position de la suite de mots `key` dans `words` (-1 si absente)."""
    n = len(key)
    for i in range(len(words) - n + 1):
        if words[i : i + n] == key:
            return i
    return -1


def resolve_vocabulary(query: str, path: str | Path | None = None) -> TargetSheet | None:
    """Objet courant nommé dans la phrase : le premier nommé, et le nom le plus long à égalité
    (« le sac à dos » plutôt que « le sac », « la télécommande de la télé » → télécommande)."""
    words = content_words(query)
    best, best_rank = None, None
    for sh in load_vocabulary(path):
        for k in sh.keys:
            kw = tuple(k.split())
            i = _find_in(words, kw)
            if i >= 0 and (best_rank is None or (i, -len(kw)) < best_rank):
                best, best_rank = sh, (i, -len(kw))
    return best


def resolve_target(
    query: str, directory: str | Path | None = None, vocabulary: bool = True
) -> TargetSheet:
    """Fiche correspondant à la phrase, sinon objet courant (`vocabulary`) ; `UnknownTarget`
    (avec la liste des cibles) sinon."""
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
        if not partial and vocabulary:  # aucune fiche : objet courant ?
            sh = resolve_vocabulary(query)
            if sh is not None:
                return sh
    known = ", ".join(f"« {s.label} »" for s in sheets) or "aucune"
    raise UnknownTarget(
        f"cible inconnue pour « {query} ». Cibles disponibles : {known}, "
        f"et les objets courants de {VOCABULARY}."
    )


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
    raw["target"]["spoken"] = sheet.spoken
    raw["target"]["plural"] = sheet.plural
    return raw


def load_config_for_target(query: str | None, path=None, overrides: dict | None = None):
    """Config avec la fiche cible appliquée (les `overrides` explicites priment sur la fiche)."""
    from visionaid.utils.config import load_config

    ov = dict(overrides or {})
    ov["target.query"] = query
    return load_config(path, ov)


# ------------------------------------------------------------------ commandes vocales
STOP_WORDS = {"stop", "arrete", "arreter", "arretes", "termine", "fini", "annule", "annuler"}
STOP_PHRASES = ("c est bon", "j ai trouve", "laisse tomber")


def parse_command(texts, directory: str | Path | None = None) -> tuple[str, TargetSheet | None]:
    """Phrase(s) reconnue(s) → (action, fiche). Action : `search`, `stop` ou `unknown`.

    Plusieurs transcriptions possibles (alternatives de la reconnaissance vocale) : la première
    qui désigne une fiche l'emporte. « Stop », « arrête », « j'ai trouvé » : fin de la recherche.
    Ensuite seulement, les objets courants (config/objects.yaml) : « arrête, c'est sur la
    table » reste un arrêt.
    """
    if isinstance(texts, str):
        texts = [texts]
    texts = [t for t in texts if t and t.strip()]
    for t in texts:
        try:
            return "search", resolve_target(t, directory, vocabulary=False)
        except UnknownTarget:
            pass
    # « c'est bon, elle est sur la table » : fin de recherche, pas une demande de table
    for t in texts:
        n = normalize(t)
        if set(n.split()) & STOP_WORDS or any(p in n for p in STOP_PHRASES):
            return "stop", None
    for t in texts:
        sh = resolve_vocabulary(t)
        if sh is not None:
            return "search", sh
    return "unknown", None


def target_raw(raw: dict, query: str) -> dict:
    """Config brute pour la cible `query`, appliquée sur la config de base (sans fiche).

    `raw["_raw_base"]` (posé par run_live) est la config sans fiche cible : on évite qu'une
    surcharge de la fiche précédente (seuil de détection des clés…) ne reste en place.
    """
    import copy

    base = raw.get("_raw_base") or raw
    out = copy.deepcopy({k: v for k, v in base.items() if k != "_raw_base"})
    for k, v in raw.items():  # réglages d'exécution (« _phone », « _stub_models »…)
        if k.startswith("_") and k != "_raw_base":
            out[k] = v
    return apply_target(out, query)


def sheet_for_config(raw: dict) -> TargetSheet | None:
    """Fiche de la cible configurée (prompt fixe), ou None."""
    q = (raw.get("target") or {}).get("query")
    if not q:
        return None
    try:
        return resolve_target(q, (raw.get("target") or {}).get("sheets_dir"))
    except UnknownTarget:
        return None


def known_targets_phrase(directory: str | Path | None = None) -> str:
    """« ta gourde ou tes clés » : ce que l'utilisateur peut demander."""
    art = {"ma": "ta", "mon": "ton", "mes": "tes"}
    names = []
    for s in load_sheets(directory):
        w = s.label.split(" ", 1)
        names.append(f"{art.get(w[0], w[0])} {w[1]}" if len(w) == 2 else s.label)
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " ou " + names[-1]
