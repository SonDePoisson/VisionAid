"""Phase 16 (données) : chaque session réelle de `data/sessions/` se lit de bout en bout."""

import pytest

from visionaid.apps.session_info import list_sessions, summarize
from visionaid.io.session import SessionImu, SessionSource, load_session
from visionaid.utils.config import load_config, resolve_path

pytestmark = pytest.mark.data


def _sessions():
    return list_sessions(resolve_path(load_config().session.dir))


@pytest.mark.parametrize("sdir", _sessions() or [None], ids=lambda p: p.name if p else "aucune")
def test_real_session_reads_fully(sdir):
    if sdir is None:
        pytest.skip("Aucune session réelle dans data/sessions/ (voir docs/checkpoint_enregistrements.md)")
    s = load_session(sdir)
    if not s.frames:  # enregistrement lancé puis arrêté avant toute image
        pytest.skip(f"session vide (enregistrement interrompu) : {sdir.name}")
    n = sum(1 for _ in SessionSource(s, width=640))
    assert n == len(s.frames) > 0
    info = summarize(s)
    print(info)
    if s.meta.get("imu_available", True):
        assert len(SessionImu(s)) > 0, "session sans IMU"
