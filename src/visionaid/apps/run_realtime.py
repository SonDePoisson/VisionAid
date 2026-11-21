"""Mode temps réel : graphe multi-processus sur le bus ZeroMQ, vidéo rejouée au rythme réel (1×).

Multi-cadence : détection à chaque frame disponible, profondeur + pose aussi vite que possible,
planification à 5 Hz, consignes à 20 Hz. Mesure les latences par étage (p50/p95), les frames
sautées et les fréquences effectives.
"""

from __future__ import annotations

import argparse
import time

from visionaid.bus.nodes import NodeSpec
from visionaid.bus.runner import GraphRunner
from visionaid.utils.config import load_raw
from visionaid.utils.logging import get_logger
from visionaid.utils.report import update_report

log = get_logger("realtime")
B = "visionaid.apps.realtime_blocks"


def graph(raw: dict) -> list[NodeSpec]:
    rt = raw["realtime"]
    return [
        NodeSpec("source", f"{B}:ReplaySourceBlock", outputs=["frame"]),
        NodeSpec(
            "perception",
            f"{B}:make_perception",
            inputs=["frame"],
            outputs=["detections"],
            trigger="frame",
            heavy_inputs=["frame"],
        ),
        NodeSpec(
            "geometry",
            f"{B}:GeometryBlock",
            inputs=["frame"],
            outputs=["depth", "pose"],
            trigger="frame",
            heavy_inputs=["frame"],
        ),
        NodeSpec(
            "world",
            f"{B}:WorldBlock",
            inputs=["depth", "pose", "detections"],
            outputs=["costmap", "object", "pose_world"],
            trigger="pose",
            heavy_inputs=["depth"],
        ),
        NodeSpec(
            "planner",
            f"{B}:make_planner",
            inputs=["costmap", "object", "pose_world"],
            outputs=["path"],
            trigger="costmap",
            rate_hz=float(rt["plan_hz"]),
            heavy_inputs=["costmap"],
        ),
        NodeSpec(
            "guidance",
            f"{B}:make_guidance",
            inputs=["pose_world", "object", "path", "costmap"],
            outputs=["cue"],
            trigger=None,  # minuteur 20 Hz sur les dernières entrées
            rate_hz=float(rt["cue_hz"]),
            heavy_inputs=["costmap"],
        ),
        NodeSpec("sink", f"{B}:CueSink", inputs=["cue"], trigger="cue"),
    ]


def run(duration_s: float | None = None, raw: dict | None = None, warmup_s: float = 25.0) -> dict:
    raw = raw or load_raw()
    duration_s = float(duration_s or raw["realtime"]["duration_s"])
    # les nœuds chargent leurs modèles pendant `warmup_s` ; la lecture démarre à t0
    raw["_t0_wall"] = time.time() + warmup_s
    specs = graph(raw)
    runner = GraphRunner(specs, raw, base_port=int(raw["bus"]["base_port"]), stop_timeout_s=10.0)
    runner.start()
    try:
        while time.time() < raw["_t0_wall"] + duration_s:
            time.sleep(0.5)
            if len(runner.alive()) < len(specs):
                log.error(
                    "Nœud(s) arrêté(s) : %s",
                    set(p.name for p in runner.procs) - set(runner.alive()),
                )
                break
        alive_at_end = runner.alive()
    finally:
        stop_s = runner.stop()
    st = runner.stats
    stage = {
        name: {
            k: v for k, v in s.items() if k in ("process", "age_in:frame", "e2e_from_trigger_send")
        }
        for name, s in st.items()
    }
    sink = st.get("sink", {}).get("_block", {})
    src = st.get("source", {})
    n_frames = src.get("_n_out", {}).get("n", 0)
    rates = {name: s.get("process", {}).get("n", 0) / duration_s for name, s in st.items()}
    summary = {
        "duration_s": duration_s,
        "nodes_alive_at_end": len(alive_at_end),
        "n_nodes": len(specs),
        "stop_time_s": stop_s,
        "frames_published": n_frames,
        "perception_processed": st.get("perception", {}).get("process", {}).get("n", 0),
        "geometry_processed": st.get("geometry", {}).get("process", {}).get("n", 0),
        "frame_skip_rate_perception": 1
        - st.get("perception", {}).get("process", {}).get("n", 0) / max(n_frames, 1),
        "frame_skip_rate_geometry": 1
        - st.get("geometry", {}).get("process", {}).get("n", 0) / max(n_frames, 1),
        "effective_hz": rates,
        "stage_latency": stage,
        "e2e_latency": sink,
        "blocks": {k: v.get("_block") for k, v in st.items() if v.get("_block")},
        "e2e_p95_target_ms": 300,
    }
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--duration", type=float, default=None)
    args = ap.parse_args(argv)
    s = run(args.duration)
    update_report("realtime", s)
    log.info("Temps réel : %s", s["e2e_latency"])
    return s


if __name__ == "__main__":
    main()
