"""Phase 22 : sons de guidage (sons enregistrés, directeur sonore, rendu, préparation)."""

import math

import numpy as np
import pytest

from visionaid.audio.director import (
    ALERT,
    GUIDE,
    SEARCH,
    SoundDirector,
    backness,
    expand_azimuth,
)
from visionaid.audio.renderer import AudioRenderer
from visionaid.bus.messages import GuidanceCue, SoundCommand, decode, encode
from visionaid.utils.config import load_config, resolve_path

pytestmark = pytest.mark.unit
DEG = math.pi / 180


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_expansion_keeps_landmarks_and_is_monotone():
    k = 1.8
    for a in (0.0, math.pi / 2, -math.pi / 2, math.pi):
        assert expand_azimuth(a, k) == pytest.approx(a, abs=1e-12)
    x = np.linspace(-math.pi, math.pi, 2001)
    y = expand_azimuth(x, k)
    assert np.all(np.diff(y) >= -1e-12)
    assert math.degrees(expand_azimuth(10 * DEG, k)) == pytest.approx(17.9, abs=0.2)
    # derrière reste derrière, devant reste devant
    assert np.all((np.abs(y) > math.pi / 2 + 1e-9) == (np.abs(x) > math.pi / 2 + 1e-9))
    assert expand_azimuth(10 * DEG, 1.0) == pytest.approx(10 * DEG)


def test_backness():
    assert backness(0.0) == 0 and backness(math.pi / 2) == pytest.approx(0, abs=1e-12)
    assert backness(math.pi) == 1 and backness(120 * DEG) == pytest.approx(1)


def _cue(t, state, az=0.0, dist=3.0):
    return GuidanceCue(t, int(t * 10), state, az, 0.0, dist, 0.0)


def test_director_modes_and_interval(cfg):
    d = SoundDirector(cfg.audio)
    assert d.command(_cue(0, "SEARCHING", 0.3)).mode == SEARCH
    c = d.command(_cue(0.1, "NAVIGATING", 0.3, 6.0))
    assert c.mode == GUIDE and c.interval_s == pytest.approx(cfg.audio.guide_interval_far_s)
    near = d.command(_cue(0.2, "APPROACHING", 0.0, 0.0))
    assert near.interval_s == pytest.approx(cfg.audio.guide_interval_near_s)
    assert d.command(_cue(0.3, "OBSTACLE_ALERT")).mode == ALERT
    assert d.command(_cue(0.4, "TRACKING_LOST")).mode == ALERT
    assert d.command(_cue(0.5, "SEARCHING")).gain_db == pytest.approx(cfg.audio.search_gain_db)


def test_director_back_is_muffled(cfg):
    d = SoundDirector(cfg.audio)
    front = d.command(_cue(0, "NAVIGATING", 0.0))
    back = d.command(_cue(0.1, "NAVIGATING", math.pi))
    assert front.lowpass_hz >= 19999 and front.back_gain_db == 0
    assert back.lowpass_hz == pytest.approx(cfg.audio.back_lowpass_hz)
    assert back.back_gain_db == pytest.approx(cfg.audio.back_gain_db)


def test_arrival_event_once_with_cooldown(cfg):
    d = SoundDirector(cfg.audio)
    seq = ["APPROACHING", "ARRIVED", "ARRIVED", "APPROACHING", "ARRIVED"]
    ev = [d.command(_cue(0.5 * i, s, 0.0, 0.4)).event for i, s in enumerate(seq)]
    assert ev == ["", "arrived", "", "", ""]  # rebond < 5 s : pas de deuxième son
    later = d.command(_cue(20.0, "APPROACHING"))
    assert later.event == ""
    assert d.command(_cue(20.5, "ARRIVED")).event == "arrived"


def test_sound_command_on_bus():
    c = SoundCommand(1.0, 3, "NAVIGATING", GUIDE, 0.2, 0.3, 2.0, 0.9, 0.0, 20000.0, 0.0, "")
    assert decode(encode(c)) == c


def _onsets(mono, fs, thresh=0.02):
    env = np.abs(mono)
    on = np.nonzero(env > thresh * env.max())[0]
    starts = [on[0]] + [b for a, b in zip(on[:-1], on[1:], strict=False) if b - a > 0.15 * fs]
    return np.array(starts) / fs


def test_render_guide_spacing_and_direction(cfg):
    r = AudioRenderer(cfg.audio)
    cues = [_cue(0.1 * k, "NAVIGATING", 60 * DEG, 6.0) for k in range(60)]
    st = r.render(cues, 0.0, 6.0)
    assert st.shape == (int(6.0 * r.fs), 2)
    # source à gauche : l'oreille gauche entend le son en avance (ITD) et au moins aussi fort
    from test_phase9_audio import xcorr_lag

    r.halo = 0.0
    dry = r.render(cues, 0.0, 6.0)
    assert xcorr_lag(dry.astype(float)) > 10
    assert np.sqrt(np.mean(st[:, 0] ** 2)) >= np.sqrt(np.mean(st[:, 1] ** 2))
    gaps = np.diff(_onsets(st[:, 0], r.fs))
    assert np.median(gaps) == pytest.approx(cfg.audio.guide_interval_far_s, abs=0.03)


def test_render_arrival_and_alert_are_centered(cfg):
    r = AudioRenderer(cfg.audio)
    cues = [_cue(0.1 * k, "OBSTACLE_ALERT", 0.0) for k in range(30)]
    st = r.render(cues, 0.0, 3.0)
    assert np.abs(st).max() > 0.01
    rms = np.sqrt(np.mean(st.astype(float) ** 2, axis=0))
    assert abs(20 * np.log10(rms[0] / rms[1])) < 0.5  # non spatialisé : centré
    arr = r.render([_cue(0.0, "APPROACHING", 0.0, 0.6), _cue(0.5, "ARRIVED", 0.0, 0.4)], 0.0, 3.0)
    assert np.abs(arr[int(0.6 * r.fs) :]).max() > 0.01  # le son d'arrivée est bien joué


def test_render_silent_without_cues(cfg):
    r = AudioRenderer(cfg.audio)
    assert np.abs(r.render([], 0.0, 1.0)).max() == 0


def test_processed_sounds_present_and_normalized(cfg):
    import json

    d = resolve_path(cfg.audio.sounds_dir)
    rep = json.loads((d / "levels.json").read_text())
    for s in ("guide", "search", "arrived", "alert"):
        f = getattr(cfg.audio.sounds, s).file
        assert (d / f).exists()
        assert rep["sounds"][f]["after"]["lufs_m"] == pytest.approx(-20.0, abs=0.5)
        assert rep["sounds"][f]["after"]["peak_dbfs"] <= -1.0 + 1e-6


def test_prepare_trims_and_normalizes():
    from visionaid.audio.prepare import momentary_loudness, prepare_one

    fs = 44100
    t = np.arange(int(0.5 * fs)) / fs
    tone = 0.01 * np.sin(2 * np.pi * 220 * t)
    x = np.concatenate([np.zeros(int(0.3 * fs)), tone, np.zeros(int(0.3 * fs))])
    y, info = prepare_one(x, fs, True, -20.0, -1.0)
    assert len(y) < 0.6 * fs  # silences coupés
    assert momentary_loudness(y, fs) == pytest.approx(-20.0, abs=0.3)
    assert abs(y[0]) < 1e-3 and abs(y[-1]) < 1e-3  # fondus


def test_search_sound_differs_from_guide(cfg):
    """Exploration (objet pas trouvé) : autre son et autre rythme que le guidage."""
    assert cfg.audio.sounds.search.file != cfg.audio.sounds.guide.file
    d = SoundDirector(cfg.audio)
    s = d.command(_cue(0.0, "SEARCHING"))
    g = d.command(_cue(0.1, "NAVIGATING", dist=10.0))
    assert s.mode == "search" and g.mode == "guide"
    assert s.interval_s == pytest.approx(cfg.audio.search_interval_s)
    assert s.interval_s > g.interval_s  # exploration plus lente que le guidage, même au loin
    r = AudioRenderer(cfg.audio)
    assert len(r.search) != len(r.guide) or not np.allclose(r.search, r.guide)
    fs = r.fs
    # 4 s de recherche puis 4 s de guidage : notes de la recherche = son `search`
    cues = [_cue(t / 10, "SEARCHING") for t in range(40)]
    cues += [_cue(4 + t / 10, "NAVIGATING", dist=2.0) for t in range(40)]
    st = r.render(cues, 0.0, 8.0)
    env = np.abs(st).sum(1)
    onsets_s = np.flatnonzero(env[: 4 * fs] > 1e-4)
    assert onsets_s.size and onsets_s[0] < 0.05 * fs
    assert np.abs(st[4 * fs : 4 * fs + int(0.1 * fs)]).max() > 0  # guidage démarre tout de suite


def test_arrival_sound_is_old_chime(cfg):
    """Son d'arrivée : l'arpège do-mi-sol-do d'avant les sons enregistrés (0,6 s)."""
    import soundfile as sf

    assert cfg.audio.sounds.arrived.file == "arrivee_arpege.wav"
    x, fs = sf.read(str(resolve_path(cfg.audio.sounds_dir) / "arrivee_arpege.wav"))
    assert abs(len(x) / fs - 0.6) < 0.02
    q = len(x) // 4
    peaks = [np.fft.rfftfreq(q, 1 / fs)[np.abs(np.fft.rfft(x[k * q : (k + 1) * q])).argmax()]
             for k in range(4)]
    assert np.allclose(peaks, [523.25, 659.25, 783.99, 1046.5], atol=10)


def test_exploration_sound_is_soft(cfg):
    """Exploration : deux notes douces sol-ré, attaque lente (pas de percussion)."""
    import soundfile as sf

    assert cfg.audio.sounds.search.file == "exploration_douce.wav"
    x, fs = sf.read(str(resolve_path(cfg.audio.sounds_dir) / "exploration_douce.wav"))
    peak = np.abs(x).max()
    assert np.abs(x[: int(0.01 * fs)]).max() < 0.5 * peak  # pas de clic au début
    h = int(0.55 * fs)
    f = [np.fft.rfftfreq(len(y), 1 / fs)[np.abs(np.fft.rfft(y)).argmax()] for y in (x[:h], x[h:])]
    assert np.allclose(f, [392.0, 587.33], atol=5)
