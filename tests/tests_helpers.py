"""Petits utilitaires partagés par les tests."""

import pytest
from conftest import ref_paths


def ref_paths_or_skip():
    p = ref_paths()
    if not p:
        pytest.skip("Aucune photo de référence")
    return p
