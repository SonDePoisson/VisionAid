"""Guidage sonore d'une session enregistrée : piste WAV (et vidéo caméra avec le son).

La session est rejouée une fois dans le pipeline offline (mêmes modules que le direct) ; les
consignes de guidage sont gardées dans `consignes.json`. Les lancements suivants ne refont que
l'audio, en quelques secondes : pratique pour régler les sons (`config/default.yaml`, section
`audio`) et réécouter aussitôt. `--recompute` rejoue la vision (après un changement du guidage).

Sorties dans `outputs/son/<session>/` : `guidage.wav` (au casque), `consignes.json`, et avec
`--video` `camera_son.mp4` (image de la caméra, son joué écrit en bas, piste sonore).

    uv run python -m visionaid.apps.render_sound data/sessions/20261121-182903_gourde_direct2 --video
"""

from __future__ import annotations

import argparse
import bisect
import dataclasses
import json
import shutil
import subprocess
from pathlib import Path

import cv2

from visionaid.bus.messages import GuidanceCue
from visionaid.utils.logging import get_logger

log = get_logger("render_sound")
CACHE = "consignes.json"


def compute_cues(session_dir) -> dict:
    """Rejoue la session (vision, carte, chemin, guidage) ; consignes horodatées + durée."""
    from visionaid.io.session import SessionImu, SessionSource, load_session
    from visionaid.perception.depth import video_depth_estimator
    from visionaid.perception.pipeline import run_video_perception
    from visionaid.perception.target import load_config_for_target
    from visionaid.pipeline import OfflinePipeline

    s = load_session(session_dir)
    cfg = load_config_for_target(s.meta.get("target") or "où est ma gourde")
    if s.camera_height_m:
        cfg.body.camera_height_m = s.camera_height_m
    dets, _ = run_video_perception(cfg, s.dir)
    by = {d.frame_idx: d for d in dets}
    pipe = OfflinePipeline(cfg, None, video_depth_estimator(cfg, s.dir), imu_source=SessionImu(s))
    src = SessionSource.from_config(cfg, s.dir)
    n = 0
    for f in src:
        pipe.step(f, by.get(f.frame_idx))
        n += 1
        if n % 100 == 0:
            log.info("Rejeu : image %d", n)
    t0 = pipe.records[0].t if pipe.records else 0.0
    return {
        "session": str(Path(session_dir).resolve().name),
        "t0": float(t0),
        "fps": float(src.fps),
        "n_frames": n,
        "duration": n / float(src.fps),
        "cues": [dataclasses.asdict(c) for c in pipe.cues],
    }


def load_or_compute(session_dir, out: Path, recompute: bool = False) -> dict:
    p = out / CACHE
    if p.exists() and not recompute:
        log.info("Consignes reprises de %s (--recompute pour rejouer la vision)", p)
        return json.loads(p.read_text())
    data = compute_cues(session_dir)
    out.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))
    return data


def caption(cmd) -> str:
    """Texte du son joué (ASCII : police OpenCV)."""
    if cmd is None:
        return "Son : silence"
    if cmd.mode in ("guide", "search"):
        p = cmd.pan
        side = (
            "centre" if abs(p) < 0.05 else f"{abs(p) * 100:.0f}% {'gauche' if p < 0 else 'droite'}"
        )
        txt = "chemin" if cmd.mode == "guide" else "recherche"
        s = f"Son : {txt}, pan {side}, une note / {cmd.interval_s:.2f} s"
        if cmd.obstacle_db > -100:
            s += f"  | obstacle {cmd.obstacle_db:.0f} dB"
        return s
    return {"lost": "Son : reperage perdu", "arrived": "Son : arrive"}.get(
        cmd.mode, "Son : silence"
    )


def write_video(session_dir, out: Path, data: dict, cmds, wav: Path, height: int = 720) -> Path:
    from visionaid.apps.export_videos import Mp4Writer
    from visionaid.io.session import SessionSource
    from visionaid.perception.target import load_config_for_target

    cfg = load_config_for_target("où est ma gourde")
    src = SessionSource.from_config(cfg, session_dir)
    ts = [c.t for c in cmds]
    silent = out / "_camera.mp4"
    w = Mp4Writer(silent, data["fps"])
    for f in src:
        k = bisect.bisect_right(ts, f.t) - 1
        cmd = cmds[k] if k >= 0 else None
        img = f.image
        s = img.shape[0] / height
        img = cv2.resize(img, (int(round(img.shape[1] / s)) // 2 * 2, height))
        cv2.rectangle(img, (0, height - 40), (img.shape[1], height), (0, 0, 0), -1)
        state = cmd.state if cmd is not None else ""
        cv2.putText(img, f"{state}  {caption(cmd)}", (10, height - 13), 0, 0.6, (255, 255, 255),
                    1, cv2.LINE_AA)  # fmt: skip
        w.write(img)
    w.close()
    video = out / "camera_son.mp4"
    if not shutil.which("ffmpeg"):
        log.warning("ffmpeg absent : vidéo muette, son séparé (%s)", wav)
        silent.replace(video)
        return video
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(wav),
            "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", str(video),
        ],
        check=True,
        timeout=600,
    )  # fmt: skip
    silent.unlink(missing_ok=True)
    return video


def main(argv=None) -> dict:
    from visionaid.audio.renderer import AudioRenderer
    from visionaid.utils.config import load_config, resolve_path

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("session", help="dossier de session (data/sessions/<date>_<nom>)")
    ap.add_argument(
        "--out", default=None, help="dossier de sortie (défaut : outputs/son/<session>)"
    )
    ap.add_argument("--recompute", action="store_true", help="rejoue la vision même si en cache")
    ap.add_argument("--video", action="store_true", help="écrit aussi camera_son.mp4")
    args = ap.parse_args(argv)
    name = Path(args.session).resolve().name
    out = resolve_path(args.out or f"outputs/son/{name}")
    data = load_or_compute(args.session, out, args.recompute)
    cues = [GuidanceCue(**c) for c in data["cues"]]
    ar = AudioRenderer(load_config().audio)
    stereo = ar.render(cues, data["t0"], data["duration"])
    wav = out / "guidage.wav"
    ar.write_wav(wav, stereo)
    cmds = ar.commands(cues)
    modes: dict[str, int] = {}
    for c in cmds:
        modes[c.mode] = modes.get(c.mode, 0) + 1
    n_ob = sum(c.obstacle_db > -100 for c in cmds)
    res = {
        "guidage": wav,
        "modes": modes,
        "obstacle_s": n_ob / max(len(cmds), 1) * data["duration"],
    }
    if args.video:
        res["video"] = write_video(args.session, out, data, cmds, wav)
    print(f"Durée {data['duration']:.1f} s, consignes : {modes}")
    print(f"Obstacle audible pendant ~{res['obstacle_s']:.1f} s")
    for k in ("guidage", "video"):
        if k in res:
            print(f"{k:8s} {res[k]}")
    return res


if __name__ == "__main__":
    main()
