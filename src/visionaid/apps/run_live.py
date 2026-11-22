"""Temps réel du téléphone jusqu'au chemin (phase 20) : graphe multi-processus + Rerun en direct.

    phone ─► perception ─────────────────────────────┐
          ─► géométrie (profondeur + VIO, IMU) ─► monde ─► planificateur ─► puits (mesures)
                                                    ├─► guidage ─► son ─► téléphone (casque)
                                                    └────────────────────► Rerun

Sources possibles :
- téléphone réel (défaut) : ouvrir l'URL affichée sur l'iPhone ;
- `--fake-phone [vidéo]` : faux téléphone (motif synthétique ou vidéo rejouée, gyroscope déduit) ;
- `--session <dossier>` : session enregistrée rejouée au rythme réel.

Exemples :
    uv run python -m visionaid.apps.run_live --target "où est ma gourde" --rerun live
    uv run python -m visionaid.apps.run_live --fake-phone data/video/appart.mp4 --duration 30
    uv run python -m visionaid.apps.run_live --session data/sessions/…_gourde_piece
"""

from __future__ import annotations

import argparse
import json
import socket
import threading
import time

from visionaid.bus.nodes import NodeSpec
from visionaid.bus.runner import GraphRunner
from visionaid.utils.config import load_raw
from visionaid.utils.logging import get_logger
from visionaid.utils.report import update_report

log = get_logger("live")
L = "visionaid.apps.live_blocks"
R = "visionaid.apps.realtime_blocks"


def graph(raw: dict, source: str = "phone", rerun: str = "off") -> list[NodeSpec]:
    """Nœuds du graphe ; `source` ∈ {phone, session}."""
    plan_hz = float(raw["realtime"]["plan_hz"])
    # demande à la voix : le téléphone publie `command` (cible changeable en cours de route)
    stt = source == "phone" and str(raw.get("_command_mode")) == "stt"
    cmd = ["command"] if stt else []
    if source == "session":
        src = NodeSpec("source", f"{R}:SessionReplayBlock", outputs=["frame", "imu"])
    else:
        # la source téléphone lit aussi la consigne sonore et l'envoie au casque (WebSocket)
        src = NodeSpec(
            "source",
            f"{L}:make_phone_source",
            inputs=["sound"],
            outputs=["frame", "imu", "clock"] + cmd,
        )
    specs = [
        src,
        NodeSpec(
            "perception",
            f"{L}:make_live_perception",
            inputs=["frame"] + cmd,
            outputs=["detections", "furniture"],
            trigger="frame",
            heavy_inputs=["frame"],
        ),
        NodeSpec(
            "geometry",
            f"{L}:LiveGeometryBlock",
            inputs=["frame", "imu"],
            outputs=["depth", "pose"],
            trigger="frame",
            heavy_inputs=["frame"],
            accumulate_inputs=["imu"],
        ),
        NodeSpec(
            "world",
            f"{L}:make_live_world",
            inputs=["depth", "pose", "detections", "furniture"] + cmd,
            outputs=["costmap", "object", "pose_world", "landmarks"],
            trigger="pose",
            heavy_inputs=["depth"],
        ),
        NodeSpec(
            "planner",
            f"{L}:LivePlannerBlock",
            inputs=["costmap", "object", "pose_world"] + cmd,
            outputs=["path"],
            trigger=None,  # minuteur : replanifie sur costmap nouvelle, chien de garde sinon
            rate_hz=plan_hz,
            heavy_inputs=["costmap"],
        ),
        NodeSpec(
            "guidance",
            f"{L}:LiveGuidanceBlock",
            inputs=["pose_world", "object", "path", "costmap", "landmarks"] + cmd,
            outputs=["cue", "sound"],
            trigger=None,  # minuteur : consigne sonore à cadence fixe sur les dernières entrées
            rate_hz=float(raw["realtime"]["cue_hz"]),
            heavy_inputs=["costmap"],
        ),
        NodeSpec(
            "path_sink",
            f"{L}:PathSink",
            inputs=["path", "object"] + (["clock"] if source == "phone" else []),
            trigger="path",
        ),
    ]
    if rerun != "off":
        specs.append(
            NodeSpec(
                "viz",
                f"{L}:RerunLiveBlock",
                inputs=[
                    "frame",
                    "detections",
                    "pose_world",
                    "costmap",
                    "object",
                    "path",
                    "depth",
                    "sound",
                    "landmarks",
                ],
                trigger="frame",
                rate_hz=10.0,
                heavy_inputs=["frame", "costmap", "depth"],
            )
        )
    return specs


def _wait_port(port: int, timeout: float) -> bool:
    t_end = time.time() + timeout
    while time.time() < t_end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def _fake_phone_thread(
    raw: dict,
    video: str | None,
    schedule: list[tuple[float, float]],
    out: dict,
    commands: list[tuple[float, str]] | None = None,
):
    """Faux téléphone : alterne connexions (durée) et pauses selon `schedule`."""
    from visionaid.phone.certs import client_ssl_context, ensure_certs
    from visionaid.phone.fake_phone import (
        FakePhone,
        run_fake_phone,
        video_frames,
        video_gyro_imu,
    )
    from visionaid.utils.config import resolve_path

    port = int(raw["_phone_https_port"])
    ssl_ctx = client_ssl_context(ensure_certs(resolve_path(raw["phone"]["certs_dir"])))
    stats = []
    for k, (run_s, pause_s) in enumerate(schedule):
        if video:
            fps, imu = video_gyro_imu(video, cache_dir=str(resolve_path(raw["paths"]["cache"])))
            frames = video_frames(video)
        else:
            import math

            import numpy as np

            fps = 15.0
            p = math.radians(20)  # scène stub : caméra inclinée de 20° vers le bas
            acc = 9.81 * np.array([0.0, math.cos(p), math.sin(p)])
            frames = _stub_frames()
            imu = lambda t, a=acc: (np.zeros(3), a)  # noqa: E731
        ph = FakePhone(
            f"https://localhost:{port}/",
            ssl_ctx,
            frames,
            imu,
            fps=fps,
            seed=k,
            clock_offset=0.7,
            commands=commands if k == 0 else None,
        )
        st = run_fake_phone(ph, run_s)
        stats.append(
            {
                "sent": st.sent_frames,
                "acks": st.acks,
                "errors": st.errors,
                "speech": st.speech,
                "heard": st.heard,
            }
        )
        time.sleep(pause_s)
    out["fake_phone"] = stats


def _stub_frames():
    """Images de la scène stub (gourde posée au sol) avec un léger bruit."""
    import cv2
    import numpy as np

    from visionaid.apps.live_blocks import STUB_BOX

    rng = np.random.default_rng(0)
    base = rng.integers(0, 255, (480, 320, 3), dtype=np.uint8)
    base = cv2.GaussianBlur(base, (3, 3), 0)
    x0, y0, x1, y1 = STUB_BOX.astype(int)
    base[y0 : y0 + 35, x0:x1] = (150, 150, 150)
    base[y0 + 35 : y1, x0:x1] = (0, 128, 255)
    while True:
        yield np.clip(base.astype(int) + rng.integers(-2, 3, base.shape), 0, 255).astype(np.uint8)


def run(
    duration_s: float = 30.0,
    raw: dict | None = None,
    source: str = "phone",
    session: str | None = None,
    fake: bool = False,
    fake_video: str | None = None,
    fake_schedule: list[tuple[float, float]] | None = None,
    rerun: str = "off",
    warmup_s: float = 25.0,
    stub_models: bool = False,
    fake_commands: list[tuple[float, str]] | None = None,
) -> dict:
    """Lance le graphe ; renvoie le résumé (fusionné dans report.json sous « live »)."""
    raw = raw or load_raw()
    raw["_phone"] = True
    raw["_imu"] = True
    raw["_rerun"] = rerun
    raw["_stub_models"] = stub_models
    out = str((raw.get("tts") or {}).get("output", "auto"))
    if out == "auto":  # voix dans le casque en direct ; sur le Mac en rejeu (pas de téléphone)
        out = "mac" if session else "phone"
    raw.setdefault("_tts", out)
    raw.setdefault("_command_mode", str((raw.get("command") or {}).get("mode", "prompt")))
    if session:
        raw["_command_mode"] = "prompt"  # rejeu : pas de téléphone pour parler
    if session:
        source = "session"
        raw["_session"] = session
        from visionaid.io.session import load_session

        h = load_session(session).camera_height_m
        if h:
            raw["body"]["camera_height_m"] = h
        raw["_live_clock"] = False
        raw["_t0_wall"] = time.time() + warmup_s
    else:
        raw["_live_clock"] = True
        if fake and "_phone_https_port" not in raw:  # ne jamais tomber sur un vrai serveur lancé
            with socket.socket() as so:
                so.bind(("127.0.0.1", 0))
                raw["_phone_https_port"] = so.getsockname()[1]
        raw.setdefault("_phone_https_port", int(raw["phone"]["https_port"]))
        raw.setdefault("_phone_http_port", int(raw["phone"]["http_port"]) if not fake else 0)
    specs = graph(raw, source, rerun)
    runner = GraphRunner(specs, raw, base_port=int(raw["bus"]["base_port"]), stop_timeout_s=10.0)
    runner.start()
    fake_out: dict = {}
    th = None
    t_start = time.time()
    total = sum(a + b for a, b in fake_schedule) if fake and fake_schedule else duration_s
    try:
        if source == "phone":
            if not _wait_port(int(raw["_phone_https_port"]), 30.0):
                raise RuntimeError("le serveur téléphone n'a pas démarré")
            if fake:
                time.sleep(min(warmup_s, 60.0))  # laisse les modèles se charger
                sched = fake_schedule or [(duration_s, 0.0)]
                th = threading.Thread(
                    target=_fake_phone_thread,
                    args=(raw, fake_video, sched, fake_out, fake_commands),
                    daemon=True,
                )
                th.start()
                t_start = time.time()
            else:
                from visionaid.phone.certs import host_names, reachable_ips, url_host

                hs = [n for n in host_names() if n.endswith(".local")]
                for h in hs + [url_host(i) for i in reachable_ips()]:
                    print(f"  ouvrir sur le téléphone : https://{h}:{raw['_phone_https_port']}/")
                t_start = time.time()
        else:
            t_start = raw["_t0_wall"]
        while time.time() < t_start + total:
            time.sleep(0.5)
            if len(runner.alive()) < len(specs):
                log.error(
                    "Nœud(s) arrêté(s) : %s", {p.name for p in runner.procs} - set(runner.alive())
                )
                break
        if th is not None:
            th.join(timeout=10)
        alive_at_end = runner.alive()
    except KeyboardInterrupt:
        alive_at_end = runner.alive()
    finally:
        stop_s = runner.stop()
    st = runner.stats
    blocks = {k: v.get("_block") for k, v in st.items() if v.get("_block")}
    rates = {
        name: s.get("process", {}).get("n", 0) / max(min(total, time.time() - t_start), 1e-6)
        for name, s in st.items()
    }
    summary = {
        "source": source if not fake else ("fake_phone_video" if fake_video else "fake_phone_stub"),
        "duration_s": duration_s,
        "nodes_alive_at_end": len(alive_at_end),
        "n_nodes": len(specs),
        "stop_time_s": stop_s,
        "path": blocks.get("path_sink", {}),
        "geometry": blocks.get("geometry", {}),
        "source_stats": blocks.get("source", {}),
        "planner": blocks.get("planner", {}),
        "guidance": blocks.get("guidance", {}),
        "effective_hz": rates,
        "stage_latency": {
            name: {
                k: v
                for k, v in s.items()
                if k == "process" or k.startswith("age_in") or k == "e2e_from_trigger_send"
            }
            for name, s in st.items()
        },
        "fake_phone": fake_out.get("fake_phone"),
        "e2e_p95_target_ms": 700,
    }
    return summary


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--duration", type=float, default=None, help="durée (s) ; défaut : illimitée")
    ap.add_argument("--target", default=None, help="prompt fixe, ex. « où sont mes clés »")
    ap.add_argument(
        "--demo",
        action="store_true",
        help="démo : un seul objet de la catégorie dans la pièce (une seule bouteille) ; il est "
        "reconnu dès sa détection, sans photos de référence ni couleur",
    )
    ap.add_argument(
        "--command",
        choices=["prompt", "stt"],
        default=None,
        help="prompt : objet fixé par --target ; stt : l'utilisateur dit ce qu'il cherche "
        "(bouton Parler du téléphone). Défaut : stt sans --target, prompt avec",
    )
    ap.add_argument(
        "--stt",
        choices=["whisper", "phone"],
        default=None,
        help="reconnaissance vocale : whisper (sur le PC, défaut) ou phone (Safari)",
    )
    ap.add_argument(
        "--tts",
        choices=["auto", "phone", "mac", "off"],
        default=None,
        help="voix des annonces : auto (casque du téléphone en direct, Mac en rejeu), phone, mac, off",
    )
    ap.add_argument("--session", default=None, help="session enregistrée à rejouer")
    ap.add_argument(
        "--fake-phone", nargs="?", const="", default=None, help="faux téléphone [vidéo]"
    )
    ap.add_argument("--rerun", choices=["off", "live", "file", "both"], default="live")
    ap.add_argument("--height", type=float, default=None, help="hauteur caméra mesurée (m ou cm)")
    ap.add_argument(
        "--record",
        default=None,
        help="enregistre aussi la session du direct (data/sessions/<date>_<nom>)",
    )
    ap.add_argument(
        "--depth-width",
        type=int,
        default=None,
        help="largeur d'entrée de la profondeur (défaut 518 ; 364 = −35 %% de latence mais "
        "guidage nettement moins précis, voir DECISIONS.md)",
    )
    args = ap.parse_args(argv)
    ov = {}
    if args.depth_width:
        ov["depth.input_width"] = args.depth_width
    if args.target:
        ov["target.query"] = args.target
    if args.height:
        from visionaid.utils.config import length_to_m

        ov["body.camera_height_m"] = length_to_m(args.height, "hauteur caméra")
    if args.stt:
        ov["command.stt"] = args.stt
    if args.tts:
        ov["tts.output"] = args.tts
    mode = args.command or ("prompt" if (args.target or args.session) else "stt")
    if mode == "prompt" and not (args.target or args.session):
        raise SystemExit("--command prompt demande --target « où est ma gourde »")
    ov["command.mode"] = mode
    if args.demo:
        ov["reid.text_only"] = True
    raw = load_raw(overrides=ov or None)
    # config sans fiche cible : base des cibles choisies à la voix (voir perception.target)
    raw["_raw_base"] = load_raw(overrides={k: v for k, v in ov.items() if k != "target.query"})
    raw["_command_mode"] = mode
    if args.record:
        if args.session:
            raise SystemExit("--record ne s'applique qu'au direct (pas au rejeu d'une session)")
        raw["_phone_record"] = args.record
        raw["_phone_meta"] = {"target": args.target, "notes": "", "command": mode}
    fake = args.fake_phone is not None
    s = run(
        args.duration or 10**7,
        raw,
        session=args.session,
        fake=fake,
        fake_video=args.fake_phone or None,
        rerun=args.rerun,
    )
    update_report("live", s)
    print(json.dumps(s["path"], indent=2, ensure_ascii=False, default=str))
    if s["nodes_alive_at_end"] < s["n_nodes"]:
        raise SystemExit("un nœud du graphe s'est arrêté (voir le journal)")
    return s


if __name__ == "__main__":
    main()
