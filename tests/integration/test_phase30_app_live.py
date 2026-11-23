"""Phase 30 : l'application pilote le guidage de bout en bout (faux téléphone, modèles stubs).

Démarrage du graphe en arrière-plan → téléphone connecté → « Démarrer » avec la gourde choisie
sur l'ordinateur → objet trouvé, distance et direction affichées → « Arrêter » → silence.
"""

from __future__ import annotations

import time

import pytest

from visionaid.app.settings import Settings

pytestmark = [pytest.mark.integration, pytest.mark.unit]


def _wait(cond, timeout: float, step: float = 0.25):
    t_end = time.time() + timeout
    while time.time() < t_end:
        v = cond()
        if v:
            return v
        time.sleep(step)
    return None


@pytest.mark.timeout(240)
def test_app_drives_guidance_end_to_end(tmp_path, monkeypatch):
    from visionaid.app.controller import AppController

    monkeypatch.setenv("VISIONAID_HOME", str(tmp_path / "home"))
    ctl = AppController(stub_models=True, fake_phone="", settings=Settings(tmp_path / "s.json"))
    ctl.raw["paths"]["outputs"] = str(tmp_path / "out")
    ctl.raw["paths"]["cache"] = str(tmp_path / "cache")
    ctl.raw["phone"]["certs_dir"] = str(tmp_path / "certs")
    ctl.start()
    try:
        assert _wait(lambda: ctl.snapshot()["engine"] in ("ready", "error"), 120)
        snap = ctl.snapshot()
        assert snap["engine"] == "ready", snap["engine_error"]
        assert _wait(lambda: ctl.snapshot()["phone"]["connected"], 60), "téléphone non connecté"

        assert ctl.action("start", {"mode": "here", "object": "gourde"})["sent"]
        seen = set()

        def found():
            g = ctl.snapshot()["guide"]
            seen.add(g["phase"])
            return g if g["phase"] in ("trouve", "route") and g["angle_deg"] is not None else None

        g = _wait(found, 90)
        assert g, f"phases vues : {seen}"
        assert g["big"].endswith(" m") and g["small"]
        assert "gourde" in g["last_speech"]
        assert g["heard"] == "je cherche ma gourde"

        assert ctl.action("stop", {})["sent"]
        assert _wait(lambda: "arrête" in (ctl.snapshot()["guide"]["last_speech"] or ""), 20), (
            ctl.snapshot()["guide"]
        )
        assert not ctl.snapshot()["guiding"]
        assert ctl.snapshot()["guide"]["phase"] == "off"
    finally:
        ctl.shutdown()
