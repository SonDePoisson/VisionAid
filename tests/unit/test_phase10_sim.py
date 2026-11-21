import math

import numpy as np
import pytest

from visionaid.sim.agent import head_pose, optimal_length, run_episode
from visionaid.sim.scenarios import SCENARIOS
from visionaid.sim.world import SimSensor
from visionaid.utils.config import load_config, resolve_path
from visionaid.utils.report import update_report

pytestmark = pytest.mark.unit


def test_head_pose_convention():
    T = head_pose(1.0, 2.0, math.pi / 2)  # regard vers +y
    assert np.allclose(T[:3, 2], [0, 1, 0], atol=1e-9)  # z caméra = avant
    assert np.allclose(T[:3, 1], [0, 0, -1])  # y caméra = bas
    assert np.allclose(T[:3, 0], [1, 0, 0], atol=1e-9)  # x caméra = droite
    assert np.isclose(np.linalg.det(T[:3, :3]), 1.0)


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenarios_valid(name):
    for seed in range(5):
        w = SCENARIOS[name](seed)
        assert w.clearance(w.start[:2]) >= 0.45
        assert math.isfinite(optimal_length(w))


def test_sensor_sees_walls():
    w = SCENARIOS["room"](0)
    pts = SimSensor(load_config().sim, np.random.default_rng(0)).scan(w, *w.start)
    assert len(pts) > 100
    assert (pts[:, 2] > 0.2).any() and (np.abs(pts[:, 2]) < 0.1).any()


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_smoke_episodes(name):
    """Fumée rapide (5 graines) : le simulateur boucle et réussit la plupart du temps."""
    cfg = load_config()
    ok = [run_episode(cfg, SCENARIOS[name](s), s, max_time=60).success for s in range(5)]
    assert sum(ok) >= 3


@pytest.mark.slow
@pytest.mark.timeout(3000)
def test_sim_statistics_100_seeds():
    """100 graines par type de scénario : succès ≥ 90 %, 0 collision dans ≥ 95 % des runs,
    ratio longueur parcourue / optimale ≤ 1,6 (médiane), replanification ≥ 90 %."""
    from visionaid.sim.evaluate import evaluate, render_examples

    cfg = load_config()
    real = resolve_path(cfg.paths.outputs) / "real_map.npz"
    scen = ("room", "corridor", "appearing") + (("real",) if real.exists() else ())
    summ, rows = evaluate(cfg, n_seeds=100, scenarios=scen, real_map_path=real)
    out = resolve_path(cfg.paths.outputs) / "sim"
    picks = [("room", 1), ("corridor", 2), ("appearing", 3)]
    vids = render_examples(cfg, out, picks, real)
    update_report("sim", {**summ, "videos": vids})
    for name in ("room", "corridor", "appearing"):
        s = summ[name]
        assert s["errors"] == 0
        assert s["success_rate"] >= 0.90, (name, s)
        assert s["collision_free_rate"] >= 0.95, (name, s)
        assert s["ratio_median"] <= 1.6, (name, s)
    # scénario d'obstacle surgissant : replanification réussie dans ≥ 90 % des cas où il est apparu
    assert summ["appearing"]["success_rate_with_event"] >= 0.90
    if "real" in summ:  # informatif : carte réelle bruitée
        update_report("sim", {"real_note": "carte réelle : informatif"})
