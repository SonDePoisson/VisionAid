"""Cerveau de l'application : préparation, graphe de guidage en arrière-plan, état affiché.

Le graphe temps réel (`visionaid.apps.run_live.graph`) tourne dans ses propres processus.
L'application le pilote par le serveur du téléphone, sur la boucle locale et avec un jeton :
`POST /control` (démarrer, arrêter, test du casque, volumes, mode avancé) et
`GET /control/state` (téléphone connecté, consigne sonore, phrases, demande entendue).
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import random
import secrets
import socket
import ssl
import threading
import time
import urllib.request
from typing import Any

from visionaid.app.prepare import Preparer, is_prepared
from visionaid.app.settings import OBJECTS, Settings, levels_db
from visionaid.utils.config import load_raw, resolve_path
from visionaid.utils.logging import get_logger

log = get_logger("app")

CAMERA_HEIGHT_M = 1.50  # hauteur du téléphone sur le torse (fixe pour la v0.1)
FOUND_SHOW_S = 4.0  # « Objet trouvé » reste affiché ce temps avant « En route »
LIVE_MAX_AGE_S = 2.5  # consigne sonore plus vieille : plus d'information de direction


def _free_port() -> int:
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        return int(so.getsockname()[1])


def _port_taken(port: int) -> bool:
    with socket.socket() as so:
        so.settimeout(0.5)
        return so.connect_ex(("127.0.0.1", port)) == 0


def phone_urls(port: int) -> list[str]:
    """Adresses à ouvrir sur le téléphone : https://visionaid.local (annoncé par le serveur du
    téléphone, dans le processus du guidage), puis les adresses IP en secours (téléphones sans
    mDNS). Sert quand le serveur ne donne pas encore ses adresses (démarrage, erreur) : on
    affiche quand même l'adresse fixe, celle que le téléphone a mémorisée."""
    from visionaid.phone.certs import reachable_ips, url_host
    from visionaid.phone.mdns import BONJOUR_HOST, available

    ips = reachable_ips()
    hosts = [BONJOUR_HOST] if available() else []
    hosts += [i for i in ips if ":" not in i] + [url_host(i) for i in ips if ":" in i]
    return [f"https://{h}:{port}/" for h in hosts] or [f"https://localhost:{port}/"]


def open_folder(path) -> bool:
    """Ouvre un dossier dans le Finder / l'Explorateur / le gestionnaire de fichiers."""
    import subprocess
    import sys

    try:
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif sys.platform.startswith("win"):
            subprocess.Popen(["explorer", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except OSError:
        return False


def de(spoken: str) -> str:
    """« le téléphone » → « du téléphone », « les clés » → « des clés », « la gourde » →
    « de la gourde »."""
    if spoken.startswith("le "):
        return "du " + spoken[3:]
    if spoken.startswith("les "):
        return "des " + spoken[4:]
    return "de " + spoken


def side_text(angle_deg: float) -> str:
    """Angle (0 = devant, négatif = gauche) → mots affichés sous la distance."""
    a = abs(angle_deg)
    side = "gauche" if angle_deg < 0 else "droite"
    if a <= 10:
        return "en face"
    if a <= 45:
        return f"légèrement à {side}"
    if a <= 120:
        return f"à {side}"
    return f"derrière, à {side}"


def fr_distance(d: float) -> str:
    return f"{d:.1f}".replace(".", ",") + " m"


class AppController:
    """État de l'application et actions de l'interface (appelées depuis le serveur local)."""

    def __init__(
        self,
        stub_models: bool = False,
        fake_phone: str | None = None,
        skip_prepare: bool = False,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.stub_models = stub_models
        self.fake_phone = fake_phone  # None : vrai téléphone ; "" : motif ; sinon vidéo
        self.token = secrets.token_urlsafe(24)
        self.raw = self._build_raw()
        self.preparer = Preparer(self.raw)
        self.preparer.on_done = self.start_engine
        self.prepared = skip_prepare or stub_models or is_prepared()
        self.engine = "stopped"  # stopped | starting | ready | error
        self.engine_error = ""
        self.runner = None
        self.phone: dict[str, Any] = {"connected": False}
        self.guiding = False  # copie de l'état du serveur du téléphone (seule référence)
        self.search_target = ""  # objet de la recherche en cours ("" : rien demandé encore)
        self.guide_t0 = 0.0
        self._found_t = 0.0
        self._last_state = ""
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._ssl: ssl.SSLContext | None = None
        self._http: urllib.request.OpenerDirector | None = None
        self._poll_thread: threading.Thread | None = None
        self._fake_out: dict = {}

    # ------------------------------------------------------------------ démarrage
    def _build_raw(self) -> dict:
        ov = {"command.mode": "stt", "body.camera_height_m": CAMERA_HEIGHT_M}
        if self.stub_models:  # tests et démonstration : scène factice (comme les tests du live)
            ov.update(
                {
                    "video.width": 320,
                    "depth.scale_factor": 1.0,
                    "phone.calib_dir": str(resolve_path(".cache/app/sans-calibration")),
                    "command.stt": "phone",
                }
            )
        raw = load_raw(overrides=ov)
        raw["_raw_base"] = load_raw(overrides=ov)
        s = self.settings.snapshot()
        fake = self.fake_phone is not None
        raw.update(
            _phone=True,
            _imu=True,
            _command_mode="stt",
            _tts="phone",
            _live_clock=True,
            _stub_models=self.stub_models,
            # mode avancé : Rerun s'ouvre au lancement de chaque recherche (jamais en test)
            _rerun="off" if fake else "search",
            _control_token=self.token,
            _levels=levels_db(s["volumes"]),
            _advanced=bool(s["advanced"]),
        )
        raw["_phone_https_port"] = _free_port() if fake else int(raw["phone"]["https_port"])
        raw["_phone_http_port"] = 0 if fake else int(raw["phone"]["http_port"])
        if fake:  # tests : jamais les ports d'un vrai guidage lancé à côté
            raw["bus"]["base_port"] = random.randint(20000, 40000)
        if s["advanced"] and s["record"]:
            raw["_phone_record"] = "application"
            raw["_phone_meta"] = {"notes": "", "command": "stt"}
        return raw

    def start(self) -> None:
        """Préparation si besoin, puis le graphe de guidage."""
        self._poll_thread = threading.Thread(target=self._poll, name="app-poll", daemon=True)
        self._poll_thread.start()
        if self.prepared:
            self.start_engine()
        else:
            self.preparer.start()

    def start_engine(self) -> None:
        self.prepared = True
        with self._lock:
            if self.engine in ("starting", "ready"):
                return
            self.engine = "starting"
            self.engine_error = ""
        threading.Thread(target=self._start_engine, name="app-engine", daemon=True).start()

    def _start_engine(self) -> None:
        from visionaid.apps.run_live import _wait_port, graph
        from visionaid.bus.runner import GraphRunner
        from visionaid.phone.certs import client_ssl_context, ensure_certs

        try:
            raw = self.raw
            port = int(raw["_phone_https_port"])
            if _port_taken(port):  # sinon on parlerait à l'ancien serveur, sans le savoir
                raise RuntimeError(
                    f"le port {port} est déjà pris : un ancien VisionAid tourne encore. "
                    "Quittez-le (ou redémarrez l'ordinateur), puis relancez"
                )
            specs = graph(raw, "phone", raw["_rerun"])
            self.runner = GraphRunner(
                specs, raw, base_port=int(raw["bus"]["base_port"]), stop_timeout_s=10.0
            )
            self.runner.start()
            if not _wait_port(port, 120.0):
                raise RuntimeError("le serveur du téléphone n'a pas démarré")
            self._ssl = client_ssl_context(ensure_certs(resolve_path(raw["phone"]["certs_dir"])))
            # requêtes locales : jamais par un proxy système (il ne verrait pas 127.0.0.1)
            self._http = urllib.request.build_opener(
                urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=self._ssl)
            )
            with self._lock:
                self.engine = "ready"
            log.info("Guidage prêt ; téléphone : %s", ", ".join(phone_urls(port)))
            if self.fake_phone is not None:
                self._start_fake_phone()
        except Exception as e:  # noqa: BLE001 - port pris, modèle manquant…
            log.exception("Démarrage du guidage impossible")
            with self._lock:
                self.engine = "error"
                self.engine_error = str(e)

    def _start_fake_phone(self) -> None:
        from visionaid.apps.run_live import _fake_phone_thread

        threading.Thread(
            target=_fake_phone_thread,
            args=(self.raw, self.fake_phone or None, [(10**6, 0.0)], self._fake_out),
            name="fake-phone",
            daemon=True,
        ).start()

    def shutdown(self) -> None:
        self._stop.set()
        if self.guiding:
            self._control({"action": "stop"})
        # le téléphone revient sur sa page de démarrage et se tait (plus de son « perdu »)
        if self._control({"action": "quit"}):
            time.sleep(0.3)  # le temps que le message parte avant la fermeture du serveur
        if self.runner is not None:
            try:
                self.runner.stop()
            except Exception as e:  # noqa: BLE001 - arrêt best effort
                log.warning("Arrêt du guidage incomplet : %s", e)
            self.runner = None

    # ------------------------------------------------------------------ téléphone
    def _url(self, path: str) -> str:
        return f"https://localhost:{int(self.raw['_phone_https_port'])}{path}"

    def _control(self, obj: dict) -> bool:
        if self.engine != "ready" or self._ssl is None:
            return False
        body = json.dumps(dict(obj, token=self.token)).encode()
        req = urllib.request.Request(
            self._url("/control"), data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with self._http.open(req, timeout=3) as r:
                return bool(json.loads(r.read()).get("sent"))
        except Exception as e:  # noqa: BLE001 - serveur en cours d'arrêt
            log.warning("Commande %s non transmise : %s", obj.get("action"), e)
            return False

    def _poll(self) -> None:
        while not self._stop.is_set():
            if self.engine == "ready" and self._ssl is not None:
                try:
                    url = self._url(f"/control/state?token={self.token}")
                    with self._http.open(url, timeout=2) as r:
                        st = json.loads(r.read())
                    with self._lock:
                        self.phone = st
                        self._follow_phone(st)
                except Exception:  # noqa: BLE001 - redémarrage du serveur : on réessaie
                    with self._lock:
                        self.phone = {"connected": False}
            if self.runner is not None and self.engine == "ready":
                if len(self.runner.alive()) < len(self.runner.procs):
                    with self._lock:
                        self.engine = "error"
                        self.engine_error = "une partie du guidage s'est arrêtée"
            self._stop.wait(0.25)

    def _follow_phone(self, st: dict) -> None:
        """L'état du guidage vient du serveur du téléphone, qui le partage avec le téléphone :
        lancé ou non, et objet cherché (choisi ici ou dit au téléphone). L'application et le
        téléphone affichent donc toujours la même situation."""
        guide = bool(st.get("guide"))
        if guide and not self.guiding:
            self.guide_t0, self._found_t, self._last_state = time.time(), 0.0, ""
        self.guiding = guide
        target = str((st.get("search") or {}).get("target") or "") if guide else ""
        if target != self.search_target:
            self._found_t, self._last_state = 0.0, ""
        self.search_target = target
        snd = st.get("sound") or {}
        state = str(snd.get("state") or "")
        if state != self._last_state:
            if self._last_state in ("", "IDLE", "SEARCHING") and state in (
                "NAVIGATING",
                "APPROACHING",
                "OBSTACLE_ALERT",
            ):
                self._found_t = time.time()
            self._last_state = state

    # ------------------------------------------------------------------ actions
    def action(self, name: str, args: dict) -> dict:
        s = self.settings
        if name == "start":
            mode = args.get("mode", s.get("mode"))
            obj = args.get("object", s.get("object"))
            s.update(mode=mode, object=obj)
            payload: dict[str, Any] = {"action": "start", "mode": mode}
            if mode == "here":
                payload["text"] = OBJECTS[obj]["phrase"]
            with self._lock:  # tout de suite à l'écran ; le serveur confirme au prochain relevé
                self.guiding, self.guide_t0 = True, time.time()
                self.search_target = obj if mode == "here" else ""
                self._found_t, self._last_state = 0.0, ""
            return {"ok": True, "sent": self._control(payload)}
        if name == "stop":
            with self._lock:
                self.guiding, self.search_target = False, ""
            return {"ok": True, "sent": self._control({"action": "stop"})}
        if name == "test_sound":
            return {"ok": True, "sent": self._control({"action": "test_sound"})}
        if name == "preview":
            return {
                "ok": True,
                "sent": self._control({"action": "preview", "sound": args.get("sound")}),
            }
        if name == "open_sessions":
            return {"ok": open_folder(resolve_path(self.raw["session"]["dir"]))}
        if name == "headset_ok":
            s.update(headset_tested=_dt.date.today().isoformat())
            return {"ok": True}
        if name == "setup_done":
            s.update(setup_done=True)
            return {"ok": True}
        if name == "settings":
            allowed = {k: v for k, v in args.items() if k in ("mode", "object", "volumes")}
            allowed.update({k: bool(v) for k, v in args.items() if k in ("advanced", "record")})
            snap = s.update(**allowed)
            if "volumes" in allowed:
                self._control({"action": "levels", "levels": levels_db(snap["volumes"])})
            if "advanced" in allowed:
                self._control({"action": "advanced", "on": bool(snap["advanced"])})
            return {"ok": True, "settings": snap}
        if name == "retry_prepare":
            self.preparer.start()
            return {"ok": True}
        if name == "restart_engine":
            if self.runner is not None:
                self.runner.stop()
                self.runner = None
            with self._lock:
                self.engine = "stopped"
                self.guiding, self.search_target = False, ""
            self.raw = self._build_raw()
            self.start_engine()
            return {"ok": True}
        return {"ok": False, "error": f"action inconnue : {name}"}

    # ------------------------------------------------------------------ état affiché
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            phone = dict(self.phone)
            guiding, t0 = self.guiding, self.guide_t0
            search_target = self.search_target
            found_t = self._found_t
            engine, engine_error = self.engine, self.engine_error
        port = int(self.raw["_phone_https_port"])
        settings = self.settings.snapshot()
        today = _dt.date.today().isoformat()
        return {
            "prepared": self.prepared,
            "prepare": self.preparer.snapshot(),
            "engine": engine,
            "engine_error": engine_error,
            "phone": {
                "connected": bool(phone.get("connected")),
                "fps": phone.get("fps"),
                "imu_hz": phone.get("imu_hz"),
                "rtt_ms": phone.get("rtt_ms"),
                "urls": (phone.get("urls") or phone_urls(port))
                if self.fake_phone is None
                else [self._url("/")],
            },
            "settings": settings,
            "headset_today": settings.get("headset_tested") == today,
            "guiding": guiding,
            "elapsed_s": int(time.time() - t0) if guiding else 0,
            "guide": self._guide_view(phone, guiding, found_t, search_target),
            "fake_phone": self.fake_phone is not None,
        }

    def _guide_view(self, phone: dict, guiding: bool, found_t: float, target: str) -> dict:
        now = float(phone.get("now") or time.time())
        heard = phone.get("heard") or {}
        speech = phone.get("speech") or {}
        snd = phone.get("sound") or {}
        fresh = snd and now - float(snd.get("wall") or 0) < LIVE_MAX_AGE_S
        state = str(snd.get("state") or "IDLE") if fresh else "IDLE"
        # objet choisi ici (OBJECTS) ou dit au téléphone (nom donné par le serveur)
        srch = phone.get("search") or {}
        obj = OBJECTS.get(target) or (srch if srch.get("spoken") else None)
        spoken = str(obj["spoken"]) if obj else "l'objet"
        plural = bool(obj and obj.get("plural"))
        fem = bool(obj and obj.get("feminine"))
        Spoken = spoken[:1].upper() + spoken[1:]
        found = "trouvé" + ("e" if fem else "") + ("s" if plural else "")

        if not guiding:
            phase = "off"
        elif state == "SEARCHING" or (state == "IDLE" and target):
            phase = "recherche"
        elif state == "IDLE":
            phase = "ecoute"
        elif state == "ARRIVED":
            phase = "arrivee"
        elif found_t and time.time() - found_t < FOUND_SHOW_S:
            phase = "trouve"
        else:
            phase = "route"

        dist = snd.get("dist") if fresh else None
        az = snd.get("az") if fresh else None
        directional = phase in ("trouve", "route", "arrivee") and az is not None
        angle = -math.degrees(float(az)) if directional else None
        texts = {
            "off": ("Prêt à guider.", ""),
            "ecoute": (
                "Qu'est-ce qu'on cherche ?",
                "La personne appuie sur Parler sur le téléphone et dit ce qu'elle cherche.",
            ),
            "recherche": (
                f"Recherche {de(spoken)}.",
                "Tourner lentement sur soi-même. Le son de recherche joue dans le casque.",
            ),
            "trouve": (
                f"{Spoken} {found}.",
                "La position est annoncée dans le casque.",
            ),
            "route": (f"En route vers {spoken}.", "Suivre le son du chemin."),
            "arrivee": (
                "Arrivé.",
                f"{Spoken} {'sont' if plural else 'est'} à portée de main.",
            ),
        }
        title, detail = texts[phase]
        if state == "TRACKING_LOST" and phase == "route":
            detail = "Repérage perdu : s'arrêter un instant, le temps de se repérer."
        elif state == "OBSTACLE_ALERT" and phase == "route":
            detail = "Obstacle proche : avancer doucement."
        if phase == "ecoute":
            big, small = "À l'écoute", "en attente"
        elif phase == "recherche":
            big, small = "Recherche…", spoken
        elif dist is not None:
            big, small = fr_distance(float(dist)), side_text(angle) if angle is not None else ""
        else:
            big, small = "…", ""
        return {
            "phase": phase,
            "state": state,
            "title": title,
            "detail": detail,
            "big": big,
            "small": small,
            "angle_deg": round(angle, 1) if angle is not None else None,
            "heard": heard.get("text") or "",
            "last_speech": speech.get("text") or "",
        }
