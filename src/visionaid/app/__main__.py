"""Point d'entrée de l'application : `visionaid` (ou `python -m visionaid.app`).

L'interface s'ouvre dans sa propre fenêtre (pywebview : WebKit sur Mac, WebView2 sous Windows,
WebKitGTK ou Qt sous Linux). Sans moteur de fenêtre disponible, elle s'ouvre dans le navigateur.
Fermer la fenêtre quitte VisionAId (guidage arrêté, téléphone déconnecté).
"""

from __future__ import annotations

import argparse
import signal
import threading
import webbrowser

from visionaid.utils.logging import get_logger

log = get_logger("app")
TITLE = "VisionAId"


def _open_window(url: str, closed: threading.Event) -> bool:
    """Fenêtre native ; False si aucun moteur de fenêtre n'est disponible."""
    import logging

    # pywebview journalise chaque moteur essayé (traces d'erreur) : notre avertissement suffit
    logging.getLogger("pywebview").setLevel(logging.CRITICAL)
    try:
        import webview
    except Exception as e:  # noqa: BLE001 - paquet absent
        log.warning("Fenêtre native indisponible (%s) : ouverture dans le navigateur", e)
        return False
    logging.getLogger("pywebview").setLevel(logging.CRITICAL)  # réglé par pywebview à l'import
    try:
        webview.create_window(
            TITLE, url, width=1280, height=860, min_size=(420, 640), background_color="#FBF6EC"
        )
        webview.start()  # bloque jusqu'à la fermeture de la fenêtre
    except Exception as e:  # noqa: BLE001 - pas de WebKitGTK/Qt/WebView2…
        log.warning("Fenêtre native indisponible (%s) : ouverture dans le navigateur", e)
        return False
    closed.set()
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="visionaid", description="VisionAId : guidage sonore.")
    ap.add_argument("--browser", action="store_true", help="ouvrir dans le navigateur")
    ap.add_argument("--no-open", action="store_true", help="n'ouvrir aucune fenêtre (tests)")
    ap.add_argument(
        "--port", type=int, default=0, help="port local de l'interface (défaut : libre)"
    )
    ap.add_argument(
        "--fake-phone",
        nargs="?",
        const="",
        default=None,
        help="faux téléphone (démonstration, tests) : motif, ou vidéo donnée",
    )
    ap.add_argument("--stub-models", action="store_true", help="modèles factices (tests)")
    ap.add_argument("--skip-prepare", action="store_true", help="ne pas vérifier les modèles")
    args = ap.parse_args(argv)

    from visionaid.app.controller import AppController
    from visionaid.app.server import AppServer

    ctl = AppController(
        stub_models=args.stub_models, fake_phone=args.fake_phone, skip_prepare=args.skip_prepare
    )
    server = AppServer(ctl, port=args.port).start()
    ctl.start()
    print(f"VisionAId : {server.url}", flush=True)

    closed = threading.Event()

    def quit_app() -> None:
        closed.set()
        try:
            import webview

            for w in list(webview.windows):
                w.destroy()
        except Exception:  # noqa: BLE001 - pas de fenêtre native
            pass

    server.on_quit = quit_app
    signal.signal(signal.SIGINT, lambda *_: closed.set())
    try:
        if not args.no_open and not args.browser and _open_window(server.url, closed):
            pass  # fenêtre fermée par la personne
        else:
            if not args.no_open:
                webbrowser.open(server.url)
            while not closed.wait(0.5):
                pass
    finally:
        log.info("Arrêt de VisionAId…")
        ctl.shutdown()
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
