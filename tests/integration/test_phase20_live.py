"""Phase 20 : graphe temps réel téléphone → chemin (faux téléphone, modèles stubs)."""

import socket

import pytest

from visionaid.utils.config import load_raw

pytestmark = [pytest.mark.integration, pytest.mark.unit]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.timeout(240)
def test_fake_phone_to_path_with_reconnection(tmp_path):
    from visionaid.apps.run_live import run

    raw = load_raw(
        overrides={
            "video.width": 320,
            "depth.scale_factor": 1.0,
            "paths.outputs": str(tmp_path / "out"),
            "paths.cache": str(tmp_path / "cache"),
            "phone.certs_dir": str(tmp_path / "certs"),
            "bus.base_port": free_port() + 20,
        }
    )
    raw["_phone_https_port"] = free_port()
    raw["_phone_http_port"] = 0
    # 12 s connecté, 3 s de coupure, 8 s reconnecté
    s = run(
        raw=raw,
        fake=True,
        fake_schedule=[(12.0, 3.0), (8.0, 0.0)],
        rerun="off",
        warmup_s=4.0,
        stub_models=True,
    )
    print(s["path"], s["geometry"], s["fake_phone"])
    assert s["nodes_alive_at_end"] == s["n_nodes"], "un nœud est tombé"
    assert s["stop_time_s"] < 10
    p = s["path"]
    assert p["first_valid_after_s"] is not None and p["first_valid_after_s"] < 60
    assert p["n_valid_paths"] > 10
    # coupure : chemin marqué invalide, puis de nouveau valide après la reconnexion
    assert p["n_invalid_paths"] >= 1
    inv = p["invalid_wall_times"]
    assert any(t > inv[0] + 1 for t in p["valid_wall_times"]), "pas de reprise après coupure"
    assert p["e2e_capture_to_path_ms_p50"] is not None
    g = s["geometry"]
    assert g["imu_calib"] in ("a priori", "calibration") and g["no_imu_frames"] < g["frames"] * 0.2
    assert len(s["fake_phone"]) == 2 and all(f["sent"] > 20 for f in s["fake_phone"])
