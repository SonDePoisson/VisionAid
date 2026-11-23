"""Serveur local de l'application (HTTP sur 127.0.0.1 uniquement) : pages + petite API JSON."""

from __future__ import annotations

import asyncio
import io
import threading
from pathlib import Path

from aiohttp import web

from visionaid.app.controller import AppController
from visionaid.utils.logging import get_logger

log = get_logger("app.server")
WEB_DIR = Path(__file__).parent / "web"


def qr_svg(text: str) -> str:
    """Code QR en SVG (carrés pleins, sans marge : l'interface l'encadre)."""
    import qrcode
    import qrcode.image.svg

    img = qrcode.make(
        text,
        image_factory=qrcode.image.svg.SvgPathFillImage,
        border=0,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
    )
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode()


class AppServer:
    """Sert l'interface et l'API ; tourne dans son propre thread (boucle asyncio dédiée)."""

    def __init__(self, controller: AppController, port: int = 0) -> None:
        self.ctl = controller
        self.port = port
        self.on_quit = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()
        self._runner: web.AppRunner | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def start(self) -> AppServer:
        self._thread = threading.Thread(target=self._run, name="app-server", daemon=True)
        self._thread.start()
        if not self._ready.wait(15):
            raise TimeoutError("le serveur de l'application n'a pas démarré")
        return self

    def stop(self) -> None:
        if self._loop is None:
            return
        fut = asyncio.run_coroutine_threadsafe(self._runner.cleanup(), self._loop)
        try:
            fut.result(5)
        except Exception:  # noqa: BLE001 - arrêt best effort
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._startup())
        self._ready.set()
        loop.run_forever()

    async def _startup(self) -> None:
        app = web.Application()
        app.router.add_get("/", self._index)
        app.router.add_get("/api/state", self._state)
        app.router.add_post("/api/action", self._action)
        app.router.add_get("/api/qr.svg", self._qr)
        app.router.add_static("/static/", WEB_DIR)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", self.port)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]  # port choisi par le système
        log.info("Application : %s", self.url)

    async def _index(self, request: web.Request) -> web.Response:
        return web.FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-store"})

    async def _state(self, request: web.Request) -> web.Response:
        return web.json_response(self.ctl.snapshot(), headers={"Cache-Control": "no-store"})

    async def _action(self, request: web.Request) -> web.Response:
        try:
            obj = await request.json()
        except (ValueError, TypeError):
            return web.json_response({"ok": False, "error": "JSON attendu"}, status=400)
        name = str(obj.get("name", ""))
        if name == "quit":
            if self.on_quit is not None:
                asyncio.get_running_loop().call_later(0.2, self.on_quit)
            return web.json_response({"ok": True})
        try:
            res = await asyncio.to_thread(self.ctl.action, name, obj.get("args") or {})
        except (KeyError, ValueError) as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        return web.json_response(res)

    async def _qr(self, request: web.Request) -> web.Response:
        text = request.query.get("text", "")
        if not text.startswith("https://"):
            return web.Response(status=400)
        return web.Response(
            text=qr_svg(text), content_type="image/svg+xml", headers={"Cache-Control": "no-store"}
        )
