"""Phase 27 : approche de l'objet — but à portée de main, marge réduite près de l'objet.

Reproduit l'essai en direct du 21/11 (18:29) : gourde sur une table, deux chaises laissant un
passage d'environ 60 cm ; le planificateur faisait faire le tour d'une autre table (7-10 m pour une
gourde à 1-2 m) car la marge de 35 cm fermait le passage et le but était pris derrière la table.
"""

from __future__ import annotations

import numpy as np
import pytest

from visionaid.bus.messages import Costmap, ObjectEstimate
from visionaid.mapping.costmap import FREE, OCC, OccupancyGrid
from visionaid.planning.planner import Planner
from visionaid.utils.config import load_config

pytestmark = pytest.mark.unit
RES = 0.05
ORIGIN = np.array([-1.0, -3.0])


def box(st, x0, x1, y0, y1):
    j0, j1 = int((x0 - ORIGIN[0]) / RES), int((x1 - ORIGIN[0]) / RES)
    i0, i1 = int((y0 - ORIGIN[1]) / RES), int((y1 - ORIGIN[1]) / RES)
    st[i0:i1, j0:j1] = OCC


def scene(gap_m: float, table_x: float = 2.6, chairs_x: float = 1.6):
    """Utilisateur en (0, 0) ; deux chaises en x≈chairs_x avec un passage de `gap_m` en y=0 ;
    table (avec la gourde) en x≈table_x ; murs latéraux à |y| = 2,5 m."""
    cfg = load_config()
    h, w = int(6 / RES), int(6 / RES)
    st = np.full((h, w), FREE, np.int8)
    box(st, chairs_x - 0.2, chairs_x + 0.2, gap_m / 2, gap_m / 2 + 0.5)  # chaise gauche
    box(st, chairs_x - 0.2, chairs_x + 0.2, -gap_m / 2 - 0.5, -gap_m / 2)  # chaise droite
    box(st, chairs_x - 0.2, chairs_x + 0.2, gap_m / 2 + 0.5, 2.2)  # rangée de tables (gauche)
    box(st, chairs_x - 0.2, chairs_x + 0.2, -2.2, -gap_m / 2 - 0.5)  # rangée de tables (droite)
    box(st, table_x, table_x + 0.6, -0.3, 0.3)  # table ronde portant la gourde
    g = OccupancyGrid(cfg.costmap)
    cm = Costmap(0.0, 0, st, g.cost(st), ORIGIN.copy(), RES)
    obj = ObjectEstimate(
        0.0, 0, np.array([table_x + 0.3, 0.0, 0.85]), np.eye(3) * 0.01, "seen", 0.9
    )
    return cfg, cm, obj, st


def clearance(st, pts):
    from scipy.ndimage import distance_transform_edt

    d = distance_transform_edt(st != OCC) * RES
    ij = np.floor((pts[:, ::-1] - ORIGIN[::-1]) / RES).astype(int)
    return float(d[ij[:, 0], ij[:, 1]].min())


def test_gap_between_chairs_near_object_is_used():
    cfg, cm, obj, st = scene(gap_m=0.60)
    p = Planner(cfg).plan(cm, np.array([0.0, 0.0]), obj)
    assert p.valid
    straight = np.linalg.norm(p.goal - [0.0, 0.0])
    assert p.length < 1.3 * straight + 0.2  # pas de grand détour
    assert np.abs(p.points[:, 1]).max() < 0.5  # passe entre les chaises (y ≈ 0)
    assert clearance(st, p.points) >= cfg.planning.approach_clearance_m - 0.06  # corps : 20 cm
    # but à portée de main, du côté de l'utilisateur (avant la table)
    assert np.linalg.norm(p.goal - obj.position[:2]) <= cfg.planning.reach_m + 0.05
    assert p.goal[0] < 2.6


def test_old_behaviour_made_the_detour():
    """Sans la phase 27 (marge 35 cm partout, but = cellule la plus proche) : détour."""
    cfg, cm, obj, _ = scene(gap_m=0.60)
    old = load_config(overrides={"planning.reach_m": 0.0, "planning.approach_zone_m": 0.0})
    p = Planner(old).plan(cm, np.array([0.0, 0.0]), obj)
    assert p.valid and np.abs(p.points[:, 1]).max() > 1.5  # contourne par les côtés


def test_too_narrow_gap_stays_closed():
    cfg, cm, obj, st = scene(gap_m=0.30)  # 30 cm : le corps ne passe pas
    p = Planner(cfg).plan(cm, np.array([0.0, 0.0]), obj)
    assert p.valid and np.abs(p.points[:, 1]).max() > 1.5  # contourne
    assert clearance(st, p.points) >= cfg.planning.approach_clearance_m - 0.06


def test_margin_unchanged_far_from_object():
    """Le même passage de 60 cm, mais loin de l'objet (> 2 m) : marge normale, contournement."""
    cfg, cm, obj, _ = scene(gap_m=0.60, chairs_x=1.0, table_x=3.4)
    obj.position[0] = 4.6  # gourde plus loin sur une grande table
    p = Planner(cfg).plan(cm, np.array([0.0, 0.0]), obj)
    assert p.valid and np.abs(p.points[:, 1]).max() > 1.5
