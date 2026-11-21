"""Phase 23 (A) : cible « probable » avant confirmation (gourde lointaine, score juste sous le seuil)."""

from __future__ import annotations

import numpy as np
import pytest

from visionaid.bus.messages import ObjectEstimate
from visionaid.perception.detector import StubDetector
from visionaid.perception.tracker import TargetTracker
from visionaid.utils.config import load_config

pytestmark = pytest.mark.unit
IMG = np.zeros((240, 320, 3), np.uint8)
BOX_A = np.array([100, 80, 140, 180], float)
BOX_B = np.array([220, 60, 260, 160], float)
TH = 0.5754  # seuil ReID calibré de la gourde


def run(tracker, seq):
    out = []
    for k, items in enumerate(seq):
        det = StubDetector({k: [(b, 0.9, "bottle") for b, _ in items]}).detect(IMG, k / 10, k)
        d = tracker.update(det, np.array([s for _, s in items]))
        out.append(d)
    return out


def test_candidate_after_persistent_near_threshold_scores():
    cfg = load_config()
    tr = TargetTracker(cfg, TH)
    res = run(tr, [[(BOX_A, 0.52)]] * 8)  # 0,52 : sous le seuil (0,575), au-dessus de 0,85 × seuil
    assert all(d.target_idx < 0 for d in res)  # jamais confirmée
    cand = [d.candidate_idx for d in res]
    assert cand[:4] == [-1, -1, -1, -1]  # persistance requise (5 images)
    assert cand[4:] == [0, 0, 0, 0]


def test_no_candidate_below_ratio_or_when_confirmed():
    cfg = load_config()
    tr = TargetTracker(cfg, TH)
    assert all(d.candidate_idx < 0 for d in run(tr, [[(BOX_A, 0.45)]] * 12))  # 0,45 < 0,49
    tr2 = TargetTracker(cfg, TH)
    res = run(tr2, [[(BOX_A, 0.52)]] * 6 + [[(BOX_A, 0.8)]] * 4)
    assert res[-1].target_idx == 0 and res[-1].candidate_idx == -1  # confirmée : plus de candidat


def test_candidate_picks_best_and_breaks_on_drop():
    cfg = load_config()
    tr = TargetTracker(cfg, TH)
    res = run(tr, [[(BOX_A, 0.50), (BOX_B, 0.54)]] * 7 + [[(BOX_A, 0.50), (BOX_B, 0.30)]])
    assert res[6].candidate_idx == 1  # B, meilleur score moyen
    assert res[7].candidate_idx != 1  # B chute : plus candidat à cette image


def _world():
    from visionaid.mapping.world_model import WorldModel

    wm = WorldModel(load_config())
    return wm


def test_world_candidate_needs_consistent_measurements():
    wm = _world()
    a = wm.cand_anchor
    for k in range(3):
        a.update_world(np.array([3.0, 1.0, 0.8]), k * 0.1, 0.5, 3.0)
    assert wm._estimate(0.3, 3).state == "unknown"  # 3 mesures < 4
    a.update_world(np.array([3.02, 1.0, 0.8]), 0.4, 0.5, 3.0)
    e = wm._estimate(0.45, 4)
    assert e.state == "candidate" and np.allclose(e.position[:2], [3.0, 1.0], atol=0.05)
    # une cible confirmée prend le relais
    wm.anchor.update_world(np.array([3.0, 1.05, 0.8]), 0.5, 1.0, 3.0)
    wm._check_candidate()
    assert wm._estimate(0.55, 5).state == "seen" and wm.n_cand_wrong == 0


def test_wrong_candidate_detected_when_confirmed_elsewhere():
    wm = _world()
    for k in range(5):
        wm.cand_anchor.update_world(np.array([3.0, 1.0, 0.8]), k * 0.1, 0.5, 3.0)
    wm.anchor.update_world(np.array([0.5, -2.0, 0.8]), 0.6, 1.0, 2.0)  # gourde ailleurs
    wm._check_candidate()
    assert wm.n_cand_wrong == 1 and wm.cand_anchor.x is None


def test_candidate_never_arrived():
    from visionaid.bus.messages import Pose
    from visionaid.guidance.cues import GuidanceEngine

    cfg = load_config()
    eng = GuidanceEngine(cfg)
    T = np.eye(4)
    T[:3, :3] = np.array([[0, 0, 1], [-1, 0, 0], [0, -1, 0]]).T  # caméra regardant +x, z haut
    T[2, 3] = 1.4
    obj_pos = np.array([0.3, 0.0, 0.8])  # à 30 cm : « arrivé » si confirmée
    states = []
    for k in range(20):
        pose = Pose(k * 0.1, k, T.copy())
        o = ObjectEstimate(k * 0.1, k, obj_pos, np.eye(3) * 0.01, "candidate", 0.5)
        states.append(eng.update(k * 0.1, k, pose, o, None, None).state)
    assert "ARRIVED" not in states and "APPROACHING" in states
    eng2 = GuidanceEngine(cfg)
    st2 = [
        eng2.update(
            k * 0.1,
            k,
            Pose(k * 0.1, k, T.copy()),
            ObjectEstimate(k * 0.1, k, obj_pos, np.eye(3) * 0.01, "seen", 0.9),
            None,
            None,
        ).state
        for k in range(20)
    ]
    assert "ARRIVED" in st2  # même scène, cible confirmée : arrivée
