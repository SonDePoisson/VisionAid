import pytest

from visionaid.utils.config import load_config, to_dict
from visionaid.utils.device import select_device

pytestmark = pytest.mark.unit


def test_config_loads():
    cfg = load_config()
    assert cfg.video.width == 640
    assert cfg.costmap.resolution_m == pytest.approx(0.05)
    assert isinstance(to_dict(cfg)["detector"]["text_prompts"], list)


def test_config_overrides():
    cfg = load_config(overrides={"video.width": 320, "guidance": {"arrived_m": 0.4}})
    assert cfg.video.width == 320
    assert cfg.guidance.arrived_m == 0.4
    assert cfg.guidance.approach_m == 1.2


def test_device_selection():
    import torch

    d = select_device("auto")
    assert d in ("mps", "cpu")
    if torch.backends.mps.is_available():
        assert d == "mps"
    assert select_device("cpu") == "cpu"
