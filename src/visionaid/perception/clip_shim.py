"""Shim du module `clip` attendu par Ultralytics pour les prompts texte de YOLOE.

Ultralytics n'utilise que `clip.clip.tokenize` (tokenizer BPE de CLIP, contexte 77) avant
d'appeler l'encodeur texte MobileCLIP TorchScript. Le paquet `clip` n'est distribué que via
GitHub ; on fournit ici un tokenizer équivalent basé sur `transformers.CLIPTokenizer`.
"""

from __future__ import annotations

import sys
import types

import torch

_TOKENIZER = None
CONTEXT_LENGTH = 77


def tokenize(texts, context_length: int = CONTEXT_LENGTH, truncate: bool = True) -> torch.Tensor:
    """Identique à `clip.tokenize` : ids int32 complétés par des zéros."""
    global _TOKENIZER
    if _TOKENIZER is None:
        from transformers import CLIPTokenizer

        _TOKENIZER = CLIPTokenizer.from_pretrained("openai/clip-vit-base-patch32")
    if isinstance(texts, str):
        texts = [texts]
    out = torch.zeros(len(texts), context_length, dtype=torch.int32)
    for i, t in enumerate(texts):
        ids = _TOKENIZER(t, add_special_tokens=True)["input_ids"]
        if len(ids) > context_length:
            if not truncate:
                raise RuntimeError(f"Texte trop long pour le contexte {context_length}: {t}")
            ids = ids[:context_length]
            ids[-1] = _TOKENIZER.eos_token_id
        out[i, : len(ids)] = torch.tensor(ids, dtype=torch.int32)
    return out


def install() -> None:
    """Enregistre `clip` dans sys.modules si le vrai paquet est absent."""
    try:
        import clip  # noqa: F401

        return
    except ImportError:
        pass
    mod = types.ModuleType("clip")
    sub = types.ModuleType("clip.clip")
    sub.tokenize = tokenize
    mod.clip = sub
    mod.tokenize = tokenize
    sys.modules["clip"] = mod
    sys.modules["clip.clip"] = sub
