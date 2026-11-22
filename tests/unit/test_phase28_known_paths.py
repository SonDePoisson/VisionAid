"""Phase 28 : chemins par les zones connues uniquement, direction du son sans saut.

Essai en direct gourde_son_live3 (22/11, log_tick 2688 de la vue Rerun) : le chemin coupait par
une zone jamais vue (noire dans la vue monde) alors qu'un passage connu (blanc) existait ; et la
direction du son sautait d'une oreille à l'autre quand le chemin changeait.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from visionaid.bus.messages import Costmap, ObjectEstimate, Path, Pose
from visionaid.guidance.cues import GuidanceEngine
from visionaid.mapping.costmap import FREE, OCC, UNKNOWN, OccupancyGrid
from visionaid.planning.planner import Planner
from visionaid.utils.config import load_config

pytestmark = pytest.mark.unit
RES = 0.05
ORIGIN = np.array([-1.0, -3.0])


def ij(x, y):
    return int((y - ORIGIN[1]) / RES), int((x - ORIGIN[0]) / RES)


def fill(st, x0, x1, y0, y1, v):
    i0, j0 = ij(x0, y0)
    i1, j1 = ij(x1, y1)
    st[i0:i1, j0:j1] = v


def costmap(st, cfg):
    return Costmap(0.0, 0, st, OccupancyGrid(cfg.costmap).cost(st), ORIGIN.copy(), RES)


def unknown_len(st, pts, skip=0.3):
    seg = np.diff(pts, axis=0)
    cum = np.r_[0.0, np.cumsum(np.hypot(seg[:, 0], seg[:, 1]))]
    s = np.arange(skip, cum[-1], 0.02)
    x, y = np.interp(s, cum, pts[:, 0]), np.interp(s, cum, pts[:, 1])
    cells = [ij(a, b) for a, b in zip(x, y, strict=True)]
    return sum(st[c] == UNKNOWN for c in cells) * 0.02


def detour_scene():
    """Utilisateur en (0, 0), objet en (4, 1). Mur en x≈2 (y de −2,2 à 0) ; au-dessus du mur,
    une bande jamais vue de 60 cm (le raccourci) ; en dessous (y ≈ −2,5), un passage connu."""
    st = np.full((int(6 / RES), int(6 / RES)), UNKNOWN, np.int8)
    fill(st, -0.5, 4.8, -2.8, 2.8, FREE)  # tout a été vu…
    fill(st, 1.7, 2.3, 0.0, 2.8, UNKNOWN)  # … sauf cette bande, au-dessus du mur
    fill(st, 1.8, 2.2, -2.2, 0.0, OCC)  # mur
    obj = ObjectEstimate(0.0, 0, np.array([4.0, 1.0, 0.8]), np.eye(3) * 0.01, "seen", 0.9)
    return st, obj


def test_path_never_goes_through_unknown():
    cfg = load_config()
    st, obj = detour_scene()
    p = Planner(cfg).plan(costmap(st, cfg), np.array([0.0, 0.0]), obj)
    assert p.valid
    assert unknown_len(st, p.points) == 0.0
    assert p.points[:, 1].min() < -1.4  # passe par le passage connu, en bas
    # avant : le raccourci par l'inconnu était choisi
    old = load_config(overrides={"planning.allow_unknown": True})
    q = Planner(old).plan(costmap(st, old), np.array([0.0, 0.0]), obj)
    assert q.valid and unknown_len(st, q.points) > 0.5


def test_no_known_route_goes_to_frontier():
    """Aucun chemin connu jusqu'à l'objet : chemin jusqu'à la limite de la zone connue."""
    cfg = load_config()
    st = np.full((int(6 / RES), int(6 / RES)), UNKNOWN, np.int8)
    fill(st, -0.5, 1.5, -0.6, 0.6, FREE)  # seuls 1,5 m devant l'utilisateur sont connus
    obj = ObjectEstimate(0.0, 0, np.array([4.0, 0.0, 0.8]), np.eye(3) * 0.01, "seen", 0.9)
    pl = Planner(cfg)
    p = pl.plan(costmap(st, cfg), np.array([0.0, 0.0]), obj)
    assert p.valid and pl.n_frontier == 1
    assert unknown_len(st, p.points, skip=0.0) == 0.0
    assert 1.2 < p.points[-1, 0] <= 1.5  # s'arrête au bord de la zone connue, vers l'objet
    assert np.linalg.norm(p.goal - p.points[-1]) < 1e-6
    off = load_config(overrides={"planning.frontier_fallback": False})
    assert not Planner(off).plan(costmap(st, off), np.array([0.0, 0.0]), obj).valid


def _pose(yaw: float) -> Pose:
    """Tête en (0, 0, 1,4) regardant dans la direction `yaw` (rad, 0 = +x)."""
    c, s = math.cos(yaw), math.sin(yaw)
    R = np.stack([[s, -c, 0.0], [0.0, 0.0, -1.0], [c, s, 0.0]], 1)  # x_cam, y_cam, z_cam
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = [0.0, 0.0, 1.4]
    return Pose(0.0, 0, T, "ok")


def _inputs(la_xy):
    st = np.full((100, 100), FREE, np.int8)
    cm = Costmap(0.0, 0, st, np.zeros(st.shape, np.float32), np.array([-2.5, -2.5]), 0.05)
    obj = ObjectEstimate(0.0, 0, np.array([3.0, 3.0, 0.8]), np.eye(3), "seen", 1.0)
    la = np.asarray(la_xy, float)
    path = Path(0.0, 0, np.array([[0.0, 0.0], la * 3]), la, np.array([3.0, 3.0]), True, 4.0)
    return obj, path, cm


def test_direction_glides_when_path_flips():
    """Le chemin bascule de 120° : le son tourne d'au plus 90°/s, sans saut."""
    cfg = load_config()
    e = GuidanceEngine(cfg)
    obj, p_left, cm = _inputs([math.cos(1.0), math.sin(1.0)])  # chemin à +57°
    _, p_right, _ = _inputs([math.cos(-1.1), math.sin(-1.1)])  # puis à −63°
    pose = _pose(0.0)
    azs = []
    for k in range(60):
        t = k * 0.05
        azs.append(e.update(t, k, pose, obj, p_left if k < 10 else p_right, cm).guide_azimuth)
    steps = np.degrees(np.abs(np.diff(azs)))
    assert steps.max() <= cfg.guidance.direction_max_rate_dps * 0.05 + 1e-6
    assert azs[9] == pytest.approx(1.0, abs=1e-3)
    assert azs[-1] == pytest.approx(-1.1, abs=0.05)  # rejoint la nouvelle direction


def test_body_rotation_not_delayed():
    """Le lissage est dans le repère monde : tourner le corps change le son tout de suite."""
    e = GuidanceEngine(load_config())
    obj, path, cm = _inputs([1.0, 0.0])  # chemin droit devant (+x)
    a0 = e.update(0.0, 0, _pose(0.0), obj, path, cm).guide_azimuth
    a1 = e.update(0.05, 1, _pose(math.radians(60)), obj, path, cm).guide_azimuth
    assert a0 == pytest.approx(0.0, abs=1e-6)
    assert a1 == pytest.approx(-math.radians(60), abs=1e-3)  # chemin maintenant à droite


def test_smoothing_never_points_into_obstacle():
    """Chemin replanifié pour éviter un obstacle surgi devant : pas de glissement, la nouvelle
    direction est prise tout de suite (sinon le son mènerait encore sur l'obstacle)."""
    e = GuidanceEngine(load_config())
    obj, p_ahead, cm = _inputs([1.0, 0.0])  # chemin droit devant (+x)
    _, p_side, _ = _inputs([math.cos(1.2), math.sin(1.2)])  # contournement à gauche
    e.update(0.0, 0, _pose(0.0), obj, p_ahead, cm)
    cm.state[50 - 4 : 50 + 5, 50 + 10 : 50 + 13] = OCC  # obstacle à 0,5 m devant
    a = e.update(0.05, 1, _pose(0.0), obj, p_side, cm).guide_azimuth
    assert a == pytest.approx(1.2, abs=1e-3) and e.n_dir_snaps == 1
