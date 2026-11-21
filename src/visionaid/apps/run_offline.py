"""Mode offline déterministe : toute la vidéo → annotated.mp4, session.rrd, guidance.wav, report.json."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np

from visionaid.audio.renderer import AudioRenderer
from visionaid.io.sources import VideoFileSource
from visionaid.perception.depth import video_depth_estimator
from visionaid.perception.pipeline import run_video_perception, unpack_masks
from visionaid.pipeline import OfflinePipeline, guidance_coherence
from visionaid.utils.config import load_config, resolve_path
from visionaid.utils.logging import get_logger
from visionaid.utils.report import update_report
from visionaid.viz.overlay import draw_overlay
from visionaid.viz.rerun_logger import RerunLogger

log = get_logger("offline")


def _ffmpeg(args: list[str], timeout: int = 600) -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True, timeout=timeout)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log.warning("ffmpeg a échoué : %s", e)
        return False


def run(
    cfg=None,
    video=None,
    out_dir=None,
    perception=None,
    depth_est=None,
    dets_list=None,
    max_frames=None,
    rerun=None,
    report_section: str | None = "offline",
) -> dict:
    """Exécute le pipeline complet ; retourne le résumé (également fusionné dans report.json)."""
    cfg = cfg or load_config()
    out = Path(out_dir or resolve_path(cfg.paths.outputs))
    out.mkdir(parents=True, exist_ok=True)
    t_start = time.perf_counter()
    src = VideoFileSource.from_config(cfg, path=video, max_frames=max_frames)
    if dets_list is None and perception is None:
        dets_list, pinfo = run_video_perception(cfg, video)
    else:
        pinfo = {}
    dets_by_idx = {d.frame_idx: d for d in (dets_list or [])}
    depth_est = depth_est or video_depth_estimator(cfg, video)
    pipe = OfflinePipeline(cfg, perception, depth_est)
    tmp_video = out / "annotated_raw.mp4"
    vw = None
    rlog = RerunLogger(out / "session.rrd", enabled=bool(cfg.viz.rerun if rerun is None else rerun))
    n = 0
    w = src.out_w
    while (f := src.read()) is not None:
        res = pipe.step(f, dets_by_idx.get(f.frame_idx) if perception is None else None)
        d = res["dets"]
        masks = unpack_masks(d, w) if d is not None else None
        img = draw_overlay(
            f.image,
            d,
            masks,
            res["cue"],
            res["costmap"],
            res["pose_world"],
            res["object"],
            res["path"],
            int(cfg.viz.minimap_px),
            int(cfg.viz.arrow_len_px),
        )
        if vw is None:
            vw = cv2.VideoWriter(
                str(tmp_video),
                cv2.VideoWriter_fourcc(*"mp4v"),
                src.fps,
                (img.shape[1], img.shape[0]),
            )
        vw.write(img)
        rlog.log(
            f,
            res["depth"],
            res["pose_world"],
            d,
            res["costmap"],
            res["object"],
            res["path"],
            res["cue"],
        )
        n += 1
    if vw is not None:
        vw.release()
    rlog.close()
    # audio synchronisé
    t0 = pipe.records[0].t if pipe.records else 0.0
    duration = n / src.fps
    ar = AudioRenderer(cfg.audio)
    stereo = ar.render(pipe.cues, t0, duration)
    wav = out / "guidance.wav"
    ar.write_wav(wav, stereo)
    annotated = out / "annotated.mp4"
    if not _ffmpeg(
        [
            "-i",
            str(tmp_video),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "23",
            str(annotated),
        ]
    ):
        shutil.copy(tmp_video, annotated)
    _ffmpeg(
        [
            "-i",
            str(annotated),
            "-i",
            str(wav),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(out / "annotated_audio.mp4"),
        ]
    )
    tmp_video.unlink(missing_ok=True)
    # carte finale
    if pipe.world.floor.ready:
        from visionaid.viz.costmap_png import render_costmap

        s = pipe.world.grid.state()
        traj = np.array([r.cam_xyz for r in pipe.records if r.cam_xyz is not None])
        pts = pipe.path.points if pipe.path is not None and pipe.path.valid else None
        cv2.imwrite(
            str(out / "costmap_offline.png"),
            render_costmap(
                s,
                pipe.world.grid.origin,
                pipe.world.grid.res,
                traj,
                pipe.records[-1].obj_xyz,
                pts,
                cost=pipe.world.grid.cost(s),
            ),
        )
    # métriques
    states: dict[str, float] = {}
    for r in pipe.records:
        states[r.state] = states.get(r.state, 0) + 1 / src.fps
    timeline = []
    for r in pipe.records:
        if not timeline or timeline[-1][1] != r.state:
            timeline.append((round(r.t, 2), r.state))
    final = pipe.records[-1] if pipe.records else None
    final_dist = (
        float(final.distance) if final is not None and np.isfinite(final.distance) else None
    )
    summary = {
        "n_frames": n,
        "duration_s": duration,
        "wall_time_s": time.perf_counter() - t_start,
        "confirmed_fraction": float(np.mean([r.target_seen for r in pipe.records]))
        if pipe.records
        else 0.0,
        "lost_fraction": float(np.mean([r.pose_quality == "lost" for r in pipe.records]))
        if pipe.records
        else 0.0,
        "state_seconds": states,
        "state_timeline": timeline,
        "final_state": final.state if final else None,
        "final_distance_m": final_dist,
        "reached_approach": any(r.state in ("APPROACHING", "ARRIVED") for r in pipe.records),
        "path_valid_fraction": float(np.mean([r.path_valid for r in pipe.records]))
        if pipe.records
        else 0.0,
        "n_plans": pipe.planner.n_plans,
        "voice_messages": pipe.engine.messages,
        "stage_latency": pipe.stats.summary(),
        "guidance_coherence": guidance_coherence(pipe.records, src.fps),
        "outputs": {
            k: str(out / k) for k in ("annotated.mp4", "session.rrd", "guidance.wav", "report.json")
        },
        "perception": pinfo,
    }
    if report_section:
        update_report(report_section, summary)
    log.info(
        "Offline terminé : %d frames, état final %s, distance %s",
        n,
        summary["final_state"],
        final_dist,
    )
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    ap.add_argument("--video", default=None)
    ap.add_argument("--max-frames", type=int, default=None)
    args = ap.parse_args(argv)
    return run(load_config(args.config), args.video, max_frames=args.max_frames)


if __name__ == "__main__":
    main()
