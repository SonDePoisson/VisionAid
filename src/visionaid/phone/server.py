"""Serveur d'acquisition (aiohttp) : page web HTTPS + WebSocket, publication et enregistrement.

Le serveur tourne dans son propre thread (boucle asyncio dédiée) pour pouvoir être piloté depuis
du code synchrone (bloc du bus, applications, tests). Les données reçues sont transmises par
rappels (`on_frame`, `on_imu`, `on_clock`) appelés dans le thread du serveur.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from aiohttp import WSMsgType, web

from visionaid.bus.messages import ClockSync, Frame, ImuBatch
from visionaid.calib.device import phone_intrinsics
from visionaid.phone.certs import CertPaths, ensure_certs, server_ssl_context
from visionaid.phone.clock import ClockEstimator
from visionaid.phone.protocol import (
    PROTOCOL_VERSION,
    ProtocolError,
    check_hello,
    imu_batch_from_json,
    unpack_frame,
)
from visionaid.phone.recorder import SessionRecorder, new_session_dir
from visionaid.utils.config import resolve_path
from visionaid.utils.logging import get_logger

log = get_logger("phone")
WEB_DIR = Path(__file__).parent / "web"


@dataclass
class ServerStats:
    """Compteurs du serveur (lus depuis un autre thread : valeurs simples uniquement)."""

    n_connections: int = 0
    n_frames: int = 0
    n_calib: int = 0
    n_imu: int = 0
    n_bad: int = 0
    n_sound: int = 0
    frame_ages: deque = field(default_factory=lambda: deque(maxlen=2000))
    frame_times: deque = field(default_factory=lambda: deque(maxlen=200))
    imu_times: deque = field(default_factory=lambda: deque(maxlen=2000))
    last_hello: dict = field(default_factory=dict)

    def rate(self, times: deque, window: float = 2.0) -> float:
        """Cadence (Hz) sur les `window` dernières secondes."""
        now = time.time()
        n = sum(1 for t in list(times) if now - t <= window)
        return n / window

    def summary(self) -> dict:
        ages = np.array(list(self.frame_ages)) if self.frame_ages else np.zeros(0)
        return {
            "n_connections": self.n_connections,
            "n_frames": self.n_frames,
            "n_calib": self.n_calib,
            "n_imu": self.n_imu,
            "n_bad": self.n_bad,
            "n_sound": self.n_sound,
            "frame_age_ms_p50": float(np.percentile(ages, 50) * 1e3) if len(ages) else None,
            "frame_age_ms_p95": float(np.percentile(ages, 95) * 1e3) if len(ages) else None,
        }


class PhoneServer:
    """Serveur HTTPS + WebSocket pour un téléphone à la fois."""

    def __init__(
        self,
        cfg,
        on_frame: Callable[[Frame], None] | None = None,
        on_imu: Callable[[ImuBatch], None] | None = None,
        on_clock: Callable[[ClockSync], None] | None = None,
        record: str | None = None,
        https_port: int | None = None,
        http_port: int | None = None,
        host: str | None = None,
        meta: dict | None = None,
    ) -> None:
        self.cfg = cfg
        pc = cfg.phone
        h = host if host is not None else pc.host
        # « auto » / vide : toutes les interfaces en IPv4 ET IPv6 (réseaux IPv6 seul)
        self.host = None if h in (None, "", "auto", "0.0.0.0", "::") else str(h)
        self.https_port = int(https_port if https_port is not None else pc.https_port)
        self.http_port = int(http_port if http_port is not None else pc.http_port)
        self.on_frame = on_frame
        self.on_imu = on_imu
        self.on_clock = on_clock
        self.record_name = record
        self.meta = dict(meta or {})
        self.recorder: SessionRecorder | None = None
        self.stats = ServerStats()
        self.clock = ClockEstimator()
        self.certs: CertPaths = ensure_certs(resolve_path(pc.certs_dir))
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._runner: web.AppRunner | None = None
        self._ws: web.WebSocketResponse | None = None
        self._gyro_units = "deg/s"
        self._error: BaseException | None = None

    # ------------------------------------------------------------------ cycle de vie
    def start(self, timeout: float = 10.0) -> PhoneServer:
        """Démarre le serveur dans un thread ; attend qu'il écoute."""
        self._thread = threading.Thread(target=self._run, name="phone-server", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout):
            raise TimeoutError("le serveur téléphone n'a pas démarré")
        if self._error is not None:
            raise RuntimeError(f"échec du démarrage du serveur : {self._error}")
        return self

    def stop(self, timeout: float = 5.0) -> None:
        """Arrête le serveur et ferme l'enregistrement."""
        if self._loop is not None and not self._stopped.is_set():
            fut = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
            try:
                fut.result(timeout)
            except Exception as e:  # arrêt best effort
                log.warning("Arrêt du serveur incomplet : %s", e)
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout)
        if self.recorder is not None:
            self.recorder.close()

    def __enter__(self) -> PhoneServer:
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._startup())
        except BaseException as e:  # ports pris, certificat illisible…
            self._error = e
            self._ready.set()
            loop.close()
            return
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
            self._stopped.set()

    async def _startup(self) -> None:
        if self.record_name:
            d = new_session_dir(resolve_path(self.cfg.session.dir), self.record_name)
            meta = {
                "protocol": PROTOCOL_VERSION,
                "camera_height_m": float(self.cfg.body.camera_height_m),
                "name": self.record_name,
            }
            meta.update(self.meta)
            self.recorder = SessionRecorder(d, meta)
            log.info("Enregistrement de la session dans %s", d)
        app = web.Application(client_max_size=16 * 1024 * 1024)
        app.router.add_get("/", self._index)
        app.router.add_get("/ws", self._websocket)
        app.router.add_get("/calib/board", self._board)
        app.router.add_get("/ca.crt", self._ca)
        app.router.add_static("/static/", WEB_DIR)
        sounds = self._sounds_dir()
        if sounds is not None:
            app.router.add_static("/sounds/", sounds)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        ssl_ctx = server_ssl_context(self.certs)
        self._ssl_ctx = ssl_ctx
        await web.TCPSite(self._runner, self.host, self.https_port, ssl_context=ssl_ctx).start()
        self._cert_task = asyncio.create_task(self._cert_watch())
        if self.http_port > 0:  # HTTP simple : uniquement pour télécharger ca.crt
            plain = web.Application()
            plain.router.add_get("/", self._ca_page)
            plain.router.add_get("/ca.crt", self._ca)
            self._plain_runner = web.AppRunner(plain, access_log=None)
            await self._plain_runner.setup()
            await web.TCPSite(self._plain_runner, self.host, self.http_port).start()
        else:
            self._plain_runner = None

    async def _cert_watch(self, period_s: float = 3.0) -> None:
        """Changement de réseau (Wi-Fi ↔ partage de connexion) : réémet le certificat pour la
        nouvelle adresse IP et le recharge à chaud (les nouvelles connexions l'utilisent)."""
        from visionaid.phone.certs import host_names, local_ips, server_cert_covers

        while True:
            await asyncio.sleep(period_s)
            try:
                names, ips = host_names(), local_ips()
                if server_cert_covers(self.certs, names, ips):
                    continue
                self.certs = ensure_certs(resolve_path(self.cfg.phone.certs_dir), names, ips)
                self._ssl_ctx.load_cert_chain(
                    str(self.certs.server_cert), str(self.certs.server_key)
                )
                log.warning(
                    "Adresse réseau changée : certificat réémis. Nouvelle adresse : %s",
                    ", ".join(self.urls()),
                )
            except Exception as e:  # ne jamais arrêter le serveur pour ça
                log.warning("Vérification du certificat impossible : %s", e)

    async def _shutdown(self) -> None:
        if getattr(self, "_cert_task", None) is not None:
            self._cert_task.cancel()
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        if self._runner is not None:
            await self._runner.cleanup()
        if getattr(self, "_plain_runner", None) is not None:
            await self._plain_runner.cleanup()

    # ------------------------------------------------------------------ pages
    async def _index(self, request: web.Request) -> web.Response:
        return web.FileResponse(WEB_DIR / "index.html")

    async def _board(self, request: web.Request) -> web.Response:
        return web.FileResponse(WEB_DIR / "board.html")

    async def _ca(self, request: web.Request) -> web.Response:
        return web.Response(
            body=self.certs.ca_cert.read_bytes(),
            content_type="application/x-x509-ca-cert",
            headers={"Content-Disposition": 'attachment; filename="visionaid-ca.crt"'},
        )

    async def _ca_page(self, request: web.Request) -> web.Response:
        html = (
            "<!doctype html><meta charset=utf-8><meta name=viewport "
            "content='width=device-width,initial-scale=1'><title>VisionAId — certificat</title>"
            "<body style='font:18px system-ui;padding:16px'><h1>VisionAId</h1>"
            "<p>1. <a href='/ca.crt'>Télécharger le certificat</a>, puis l'installer "
            "(Réglages → Général → VPN et gestion de l'appareil).</p>"
            "<p>2. Activer la confiance totale : Réglages → Général → Informations → "
            "Réglages des certificats.</p>"
            f"<p>3. Ouvrir <b>https://{_url_host(request.url.host or 'localhost')}:"
            f"{self.https_port}/</b>.</p>"
        )
        return web.Response(text=html, content_type="text/html")

    # ------------------------------------------------------------------ WebSocket
    async def _send(self, ws: web.WebSocketResponse, obj: dict) -> None:
        if not ws.closed:
            try:
                await ws.send_str(json.dumps(obj))
            except (ConnectionResetError, RuntimeError):
                pass

    async def _websocket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=5.0, max_msg_size=16 * 1024 * 1024)
        await ws.prepare(request)
        old, self._ws = self._ws, ws
        if old is not None and not old.closed:  # un seul téléphone : le nouveau remplace l'ancien
            await self._send(old, {"type": "error", "message": "remplacé par une autre connexion"})
            await old.close()
        self.stats.n_connections += 1
        log.info("Téléphone connecté depuis %s", request.remote)
        greeted = False
        stats_task = asyncio.create_task(self._stats_loop(ws))
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        obj = json.loads(msg.data)
                    except json.JSONDecodeError:
                        self.stats.n_bad += 1
                        continue
                    if not greeted:
                        try:
                            check_hello(obj)
                        except ProtocolError as e:
                            await self._send(ws, {"type": "error", "message": str(e)})
                            await ws.close()
                            break
                        greeted = True
                        self._on_hello(obj)
                        await self._send(ws, self._welcome())
                        continue
                    await self._on_text(ws, obj)
                elif msg.type == WSMsgType.BINARY:
                    if not greeted:
                        await self._send(ws, {"type": "error", "message": "« hello » attendu"})
                        await ws.close()
                        break
                    await self._on_binary(ws, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    log.warning("Erreur WebSocket : %s", ws.exception())
        finally:
            stats_task.cancel()
            if self._ws is ws:
                self._ws = None
            log.info("Téléphone déconnecté")
        return ws

    def _sounds_dir(self) -> Path | None:
        a = getattr(self.cfg, "audio", None)
        d = resolve_path(a.sounds_dir) if a is not None and getattr(a, "sounds_dir", None) else None
        return d if d is not None and d.is_dir() else None

    def _audio_settings(self) -> dict | None:
        """Réglages du rendu sonore du téléphone (section `audio` de la config)."""
        a = getattr(self.cfg, "audio", None)
        if a is None or self._sounds_dir() is None:
            return None
        snd = a.sounds
        return {
            "sounds": {k: f"/sounds/{getattr(snd, k).file}" for k in ("guide", "arrived", "alert")},
            "gains_db": {k: float(getattr(snd, k).gain_db) for k in ("guide", "arrived", "alert")},
            "guide_notes": int(a.guide_notes),
            "guide_note_s": float(a.guide_note_s),
            "fade_in_s": float(a.guide_fade_in_s),
            "fade_out_s": float(a.guide_fade_out_s),
            "halo_mix": float(a.halo_mix),
            "master_gain_db": float(a.master_gain_db),
            "panning": "HRTF" if str(a.panning).lower() == "hrtf" else "equalpower",
            "smoothing_s": float(a.smoothing_s),
            "alert_period_s": float(a.alert_period_s),
            "watchdog_s": float(a.watchdog_s),
        }

    def send_sound(self, cmd) -> bool:
        """Envoie une `SoundCommand` au téléphone (appelable depuis n'importe quel thread)."""
        ws, loop = self._ws, self._loop
        if ws is None or ws.closed or loop is None:
            return False
        msg = {
            "type": "sound",
            "t": float(cmd.t),
            "state": cmd.state,
            "mode": cmd.mode,
            "az": round(float(cmd.azimuth_render), 4),
            "az_raw": round(float(cmd.azimuth), 4),
            "dist": float(cmd.distance) if np.isfinite(cmd.distance) else None,
            "interval": round(float(cmd.interval_s), 3),
            "gain_db": round(float(cmd.gain_db), 2),
            "lowpass_hz": round(float(cmd.lowpass_hz), 1),
            "back_gain_db": round(float(cmd.back_gain_db), 2),
            "event": cmd.event,
        }
        asyncio.run_coroutine_threadsafe(self._send(ws, msg), loop)
        self.stats.n_sound += 1
        return True

    def _welcome(self) -> dict:
        pc = self.cfg.phone
        return {
            "audio": self._audio_settings(),
            "type": "welcome",
            "protocol": PROTOCOL_VERSION,
            "session": self.recorder.dir.name if self.recorder else None,
            "max_fps": float(pc.max_fps),
            "jpeg_quality": float(pc.jpeg_quality),
            "imu_batch_ms": int(pc.imu_batch_ms),
            "capture_width": int(pc.capture_width),
            "capture_height": int(pc.capture_height),
            "ack_timeout_s": float(pc.ack_timeout_s),
            "ping_interval_s": float(pc.ping_interval_s),
        }

    def _on_hello(self, obj: dict) -> None:
        self._gyro_units = obj.get("gyro_units", "deg/s")
        self.stats.last_hello = obj
        if self.recorder is not None:
            self.recorder.update_meta(
                ua=obj.get("ua"),
                camera=obj.get("camera"),
                gyro_units=self._gyro_units,
                imu_available=obj.get("imu"),
            )

    async def _on_text(self, ws: web.WebSocketResponse, obj: dict) -> None:
        typ = obj.get("type")
        now = time.time()
        if typ == "imu":
            batch = imu_batch_from_json(obj.get("samples", []), self._gyro_units, now)
            if len(batch):
                self.stats.n_imu += len(batch)
                for _ in range(len(batch)):
                    self.stats.imu_times.append(now)
                if self.recorder is not None:
                    self.recorder.imu(batch)
                if self.on_imu is not None:
                    self.on_imu(batch)
        elif typ == "ping":
            try:
                t_phone = float(obj["t_phone"])
            except (KeyError, TypeError, ValueError):
                self.stats.n_bad += 1
                return
            self.clock.ping(obj.get("id"), t_phone, now)
            rtt = obj.get("rtt")
            if rtt is not None:
                try:
                    self.clock.rtt(obj.get("prev_id"), float(rtt))
                except (TypeError, ValueError):
                    pass
            c = self.clock.estimate(now)
            await self._send(
                ws, {"type": "pong", "id": obj.get("id"), "t_phone": t_phone, "t_pc": now}
            )
            if self.recorder is not None:
                self.recorder.clock(c)
            if self.on_clock is not None:
                self.on_clock(c)
        elif typ == "bye":
            await ws.close()
        elif typ == "notes" and self.recorder is not None:
            self.recorder.update_meta(notes=str(obj.get("text", ""))[:2000])
        else:
            self.stats.n_bad += 1

    async def _on_binary(self, ws: web.WebSocketResponse, data: bytes) -> None:
        t_recv = time.time()
        try:
            pkt = unpack_frame(data)
        except ProtocolError as e:
            self.stats.n_bad += 1
            log.debug("Image rejetée : %s", e)
            return
        if self.recorder is not None:
            self.recorder.frame(pkt.seq, pkt.t_phone, t_recv, pkt.w, pkt.h, pkt.jpeg, pkt.calib)
        if pkt.calib:
            self.stats.n_calib += 1
            await self._send(ws, {"type": "ack", "seq": pkt.seq})
            return
        self.stats.n_frames += 1
        self.stats.frame_times.append(t_recv)
        c = self.clock.estimate(t_recv)
        if np.isfinite(c.uncertainty):
            self.stats.frame_ages.append(t_recv - (pkt.t_phone + c.offset))
        try:
            if self.on_frame is not None:
                img = decode_jpeg(pkt.jpeg, int(self.cfg.video.width))
                if img is None:
                    self.stats.n_bad += 1
                    return
                h, w = img.shape[:2]
                K = self._K(w, h)
                self.on_frame(Frame(pkt.t_phone, pkt.seq, img, K, pkt.t_phone, t_recv))
        finally:
            # acquittement après ingestion : le téléphone ne va jamais plus vite que le PC,
            # et l'image suivante est saisie au moment où le PC est prêt (pas de file d'attente)
            await self._send(ws, {"type": "ack", "seq": pkt.seq})

    async def _stats_loop(self, ws: web.WebSocketResponse) -> None:
        while not ws.closed:
            await asyncio.sleep(1.0)
            c = self.clock.estimate()
            ages = list(self.stats.frame_ages)[-30:]
            await self._send(
                ws,
                {
                    "type": "stats",
                    "fps_in": round(self.stats.rate(self.stats.frame_times), 1),
                    "imu_hz": round(self.stats.rate(self.stats.imu_times), 1),
                    "offset_ms": round(c.offset * 1e3, 1) if np.isfinite(c.uncertainty) else None,
                    "rtt_ms": round(c.rtt * 1e3, 1) if c.rtt else None,
                    "frame_age_ms": round(float(np.median(ages)) * 1e3, 1) if ages else None,
                    "recording": self.recorder is not None,
                },
            )

    # ------------------------------------------------------------------ utilitaires
    def _K(self, w: int, h: int) -> np.ndarray:
        """Intrinsèques (calibration de l'appareil si présente), mises en cache par taille."""
        cache = self.__dict__.setdefault("_K_cache", {})
        if (w, h) not in cache:
            cache[(w, h)] = phone_intrinsics(self.cfg, w, h).K
        return cache[(w, h)]

    def urls(self) -> list[str]:
        """URLs HTTPS à ouvrir sur le téléphone : nom Bonjour (.local) d'abord, puis adresses."""
        from visionaid.phone.certs import host_names, reachable_ips, url_host

        hosts = [n for n in host_names() if n.endswith(".local")]
        ips = reachable_ips()
        hosts += [i for i in ips if ":" not in i] + [url_host(i) for i in ips if ":" in i]
        return [f"https://{h}:{self.https_port}/" for h in hosts] or [
            f"https://localhost:{self.https_port}/"
        ]

    def summary(self) -> dict[str, Any]:
        s = self.stats.summary()
        c = self.clock.estimate()
        s["clock_offset_s"] = c.offset if np.isfinite(c.uncertainty) else None
        s["clock_uncertainty_s"] = c.uncertainty if np.isfinite(c.uncertainty) else None
        s["session_dir"] = str(self.recorder.dir) if self.recorder else None
        return s


def _url_host(h: str) -> str:
    return f"[{h}]" if ":" in h else h


def decode_jpeg(jpeg: bytes, max_width: int) -> np.ndarray | None:
    """JPEG → image BGR, réduite à `max_width` au plus (jamais agrandie)."""
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    if w > max_width:
        nh = int(round(h * max_width / w))
        img = cv2.resize(img, (max_width, nh), interpolation=cv2.INTER_AREA)
    return img
