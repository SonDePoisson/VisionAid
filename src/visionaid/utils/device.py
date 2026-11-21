"""Sélection centralisée du device torch."""

from __future__ import annotations


def select_device(preference: str = "auto") -> str:
    """Retourne 'mps' si disponible (ou demandé et disponible), sinon 'cpu'."""
    try:
        import torch
    except ImportError:  # pragma: no cover
        return "cpu"
    mps_ok = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
    if preference == "cpu":
        return "cpu"
    if preference in ("auto", "mps"):
        return "mps" if mps_ok else "cpu"
    return "cpu"
