"""Acquisition seule : démarre le serveur téléphone, affiche l'URL (QR code) et enregistre si demandé.

Exemples :
    uv run python -m visionaid.apps.run_phone                      # flux en direct, sans enregistrer
    uv run python -m visionaid.apps.run_phone --record gourde_piece --target "où est ma gourde"
"""

from __future__ import annotations

import argparse
import json
import time

from visionaid.phone.server import PhoneServer
from visionaid.utils.config import load_config
from visionaid.utils.logging import get_logger

log = get_logger("run_phone")


def print_qr(url: str) -> None:
    """Affiche un QR code de l'URL dans le terminal (généré localement)."""
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except Exception as e:  # terminal sans unicode, etc.
        log.debug("QR code indisponible : %s", e)


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--record", default=None, help="nom de la session à enregistrer")
    ap.add_argument("--target", default=None, help="prompt fixe (consigné dans la session)")
    ap.add_argument("--height", type=float, default=None, help="hauteur caméra mesurée (m)")
    ap.add_argument("--notes", default="", help="notes libres de la session")
    ap.add_argument("--duration", type=float, default=None, help="arrêt automatique (s)")
    args = ap.parse_args(argv)
    overrides = {}
    if args.height:
        overrides["body.camera_height_m"] = args.height
    cfg = load_config(overrides=overrides)
    meta = {"target": args.target, "notes": args.notes}
    srv = PhoneServer(cfg, record=args.record, meta=meta).start()
    urls = srv.urls()
    print("\n=== VisionAId : ouvrez sur le téléphone (même réseau Wi-Fi) ===")
    for u in urls:
        print("  ", u)
    print_qr(urls[0])
    if srv.http_port > 0:
        host = urls[0].split("//")[1].split(":")[0]
        print(
            f"Certificat à installer une fois : http://{host}:{srv.http_port}/  (docs/phone_setup.md)"
        )
    print("Ctrl+C pour arrêter.\n")
    t0 = time.time()
    try:
        while args.duration is None or time.time() - t0 < args.duration:
            time.sleep(2.0)
            s = srv.stats
            log.info(
                "images %d (%.1f/s) | IMU %d (%.0f Hz) | âge p50 %s ms",
                s.n_frames,
                s.rate(s.frame_times),
                s.n_imu,
                s.rate(s.imu_times),
                (f"{s.summary()['frame_age_ms_p50']:.0f}" if s.frame_ages else "–"),
            )
    except KeyboardInterrupt:
        pass
    finally:
        srv.stop()
    summ = srv.summary()
    print(json.dumps(summ, indent=2, ensure_ascii=False))
    return summ


if __name__ == "__main__":
    main()
