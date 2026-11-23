"""Phase 30 : application de l'ordinateur (paquet installable, réglages, état affiché, pilotage)."""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
import zipfile

import pytest

from visionaid.app.settings import OBJECTS, VOLUME_DEFAULTS, Settings, levels_db, volume_db
from visionaid.utils import config as config_mod
from visionaid.utils.config import ROOT, load_config

pytestmark = pytest.mark.unit

NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ------------------------------------------------------------------ paquet installable
def test_resolve_path_installed_layout(monkeypatch, tmp_path):
    """Installé : config/ et assets/ viennent du paquet, le reste du dossier utilisateur."""
    res, home = tmp_path / "res", tmp_path / "home"
    monkeypatch.setattr(config_mod, "RESOURCES", res)
    monkeypatch.setattr(config_mod, "ROOT", home)
    assert config_mod.resolve_path("config/default.yaml") == res / "config/default.yaml"
    assert config_mod.resolve_path("assets/sounds/processed") == res / "assets/sounds/processed"
    assert config_mod.resolve_path("outputs/x.json") == home / "outputs/x.json"
    assert config_mod.resolve_path(".certs") == home / ".certs"
    assert config_mod.resolve_path(tmp_path / "abs") == tmp_path / "abs"


def test_user_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv("VISIONAID_HOME", str(tmp_path / "vh"))
    assert config_mod.user_dir() == tmp_path / "vh"


def test_source_checkout_detected():
    assert config_mod.SOURCE_CHECKOUT
    assert config_mod.DEFAULT_CONFIG == ROOT / "config" / "default.yaml"


@pytest.mark.timeout(180)
def test_wheel_ships_config_sounds_and_interfaces(tmp_path):
    """La wheel contient tout ce qu'il faut pour tourner hors du dépôt."""
    import subprocess

    r = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=170,
    )
    if r.returncode != 0:
        pytest.skip(f"uv build indisponible : {r.stderr[-300:]}")
    wheel = next(tmp_path.glob("visionaid-*.whl"))
    names = set(zipfile.ZipFile(wheel).namelist())
    for need in (
        "visionaid/_data/config/default.yaml",
        "visionaid/_data/config/targets/gourde.yaml",
        "visionaid/_data/config/targets/cles.yaml",
        "visionaid/_data/assets/sounds/processed/chemin.wav",
        "visionaid/app/web/index.html",
        "visionaid/app/web/fonts/lexend.woff2",
        "visionaid/phone/web/index.html",
    ):
        assert need in names, need
    entry = [n for n in names if n.endswith("entry_points.txt")]
    text = zipfile.ZipFile(wheel).read(entry[0]).decode()
    assert "visionaid = visionaid.app.__main__:main" in text


# ------------------------------------------------------------------ réglages
def test_volume_mapping():
    for k, v in VOLUME_DEFAULTS.items():
        assert volume_db(k, v) == 0.0  # réglage d'origine = niveau d'origine
    assert volume_db("chemin", 0) == -120.0
    assert volume_db("chemin", 100) > 0 > volume_db("chemin", 35)
    assert set(levels_db(VOLUME_DEFAULTS)) == set(VOLUME_DEFAULTS)


def test_settings_roundtrip_and_validation(tmp_path):
    p = tmp_path / "s.json"
    s = Settings(p)
    assert s.get("mode") == "voice" and not s.get("setup_done")
    s.update(mode="here", object="cles", volumes={"chemin": 150, "voix": -3, "inconnu": 5})
    again = Settings(p)
    assert again.get("mode") == "here" and again.get("object") == "cles"
    vols = again.get("volumes")
    assert vols["chemin"] == 100 and vols["voix"] == 0 and "inconnu" not in vols
    with pytest.raises(ValueError):
        s.update(mode="autre")
    with pytest.raises(KeyError):
        s.update(nimporte=1)


# ------------------------------------------------------------------ état affiché pendant le guidage
@pytest.fixture()
def ctl(tmp_path):
    from visionaid.app.controller import AppController

    return AppController(stub_models=True, fake_phone="", settings=Settings(tmp_path / "s.json"))


def _phone(state=None, az=0.0, dist=2.43, heard=None, age=0.1):
    now = time.time()
    p = {"connected": True, "now": now, "speech": {"text": "La gourde est devant toi."}}
    if state is not None:
        p["sound"] = {"state": state, "az": az, "dist": dist, "wall": now - age}
    if heard is not None:
        p["heard"] = heard
    return p


def test_guide_view_phases(ctl):
    s = ctl.settings.snapshot()
    gourde = {"text": "je cherche ma gourde", "action": "search", "target": "gourde"}
    assert ctl._guide_view(_phone(), False, 0, s)["phase"] == "off"
    v = ctl._guide_view(_phone("IDLE"), True, 0, s)
    assert v["phase"] == "ecoute" and v["angle_deg"] is None
    v = ctl._guide_view(_phone("SEARCHING", heard=gourde), True, 0, s)
    assert v["phase"] == "recherche" and v["title"] == "Recherche de la gourde."
    v = ctl._guide_view(_phone("NAVIGATING", heard=gourde), True, time.time(), s)
    assert v["phase"] == "trouve"
    # azimut positif = à gauche → angle affiché négatif
    v = ctl._guide_view(_phone("NAVIGATING", az=0.6, heard=gourde), True, time.time() - 60, s)
    assert v["phase"] == "route" and v["big"] == "2,4 m"
    assert v["angle_deg"] < 0 and v["small"] == "légèrement à gauche"
    assert v["title"] == "En route vers la gourde."
    cles = {"text": "où sont mes clés", "action": "search", "target": "cles"}
    v = ctl._guide_view(_phone("ARRIVED", heard=cles), True, time.time() - 60, s)
    assert v["phase"] == "arrivee" and v["detail"] == "Les clés sont à portée de main."
    # consigne trop ancienne (téléphone coupé) : plus de direction affichée
    v = ctl._guide_view(_phone("NAVIGATING", heard=gourde, age=10), True, time.time() - 60, s)
    assert v["angle_deg"] is None


def test_side_text_and_distance():
    from visionaid.app.controller import fr_distance, side_text

    assert side_text(0) == "en face"
    assert side_text(-30) == "légèrement à gauche"
    assert side_text(90) == "à droite"
    assert side_text(-170) == "derrière, à gauche"
    assert fr_distance(0.46) == "0,5 m"


def test_start_here_sends_object_phrase(ctl, monkeypatch):
    sent = []
    monkeypatch.setattr(ctl, "_control", lambda obj: sent.append(obj) or True)
    ctl.action("start", {"mode": "here", "object": "cles"})
    assert sent[-1] == {"action": "start", "mode": "here", "text": OBJECTS["cles"]["phrase"]}
    assert ctl.guiding
    ctl.action("stop", {})
    assert sent[-1] == {"action": "stop"} and not ctl.guiding
    ctl.action("settings", {"volumes": {"chemin": 35}})
    assert sent[-1]["action"] == "levels" and sent[-1]["levels"]["chemin"] < 0


def test_follow_spoken_requests(ctl):
    """Demande dite au téléphone : l'application passe en guidage ; « stop » l'arrête."""
    ctl._follow_phone({"heard": {"action": "search", "wall": 1.0}})
    assert ctl.guiding
    ctl._follow_phone({"heard": {"action": "stop", "wall": 2.0}})
    assert not ctl.guiding


# ------------------------------------------------------------------ pilotage du serveur du téléphone
def test_phone_server_control_requires_token(tmp_path):
    from visionaid.phone.certs import client_ssl_context
    from visionaid.phone.server import PhoneServer

    cfg = load_config(
        overrides={
            "phone.certs_dir": str(tmp_path / "certs"),
            "phone.host": "127.0.0.1",
            "phone.calib_dir": str(tmp_path / "calib"),
        }
    )
    got = []
    port = free_port()
    with PhoneServer(
        cfg, https_port=port, http_port=0, on_control=got.append, control_token="secret"
    ) as srv:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=client_ssl_context(srv.certs)),
        )

        def post(obj):
            req = urllib.request.Request(
                f"https://localhost:{port}/control",
                data=json.dumps(obj).encode(),
                headers={"Content-Type": "application/json"},
            )
            with opener.open(req, timeout=5) as r:
                return json.loads(r.read())

        with pytest.raises(urllib.error.HTTPError) as e:
            post({"token": "faux", "action": "stop"})
        assert e.value.code == 403
        assert post({"token": "secret", "action": "levels", "levels": {"chemin": -3}})["ok"]
        assert srv.levels == {"chemin": -3.0} and srv._welcome()["levels"] == {"chemin": -3.0}
        post({"token": "secret", "action": "start", "mode": "here", "text": "où sont mes clés"})
        assert got and got[-1]["text"] == "où sont mes clés" and srv.guide
        with opener.open(f"https://localhost:{port}/control/state?token=secret", timeout=5) as r:
            st = json.loads(r.read())
        assert st["ok"] and st["connected"] is False and st["guide"] is True
        with pytest.raises(urllib.error.HTTPError):
            opener.open(f"https://localhost:{port}/control/state?token=", timeout=5)


# ------------------------------------------------------------------ API locale de l'application
class _FakeCtl:
    def __init__(self):
        self.calls = []

    def snapshot(self):
        return {"prepared": True, "engine": "ready"}

    def action(self, name, args):
        self.calls.append((name, args))
        return {"ok": True}


def test_app_server_api_and_qr():
    from visionaid.app.server import AppServer

    fake = _FakeCtl()
    srv = AppServer(fake).start()
    try:
        with NO_PROXY.open(srv.url + "api/state", timeout=5) as r:
            assert json.loads(r.read())["engine"] == "ready"
        req = urllib.request.Request(
            srv.url + "api/action",
            data=json.dumps({"name": "start", "args": {"mode": "voice"}}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with NO_PROXY.open(req, timeout=5) as r:
            assert json.loads(r.read())["ok"]
        assert fake.calls == [("start", {"mode": "voice"})]
        with NO_PROXY.open(srv.url + "api/qr.svg?text=https%3A%2F%2F192.168.1.2%3A8443%2F") as r:
            assert b"<svg" in r.read()
        with NO_PROXY.open(srv.url, timeout=5) as r:
            html = r.read().decode()
        assert "Connecter le téléphone." in html and "iPhone</strong>" not in html
    finally:
        srv.stop()
