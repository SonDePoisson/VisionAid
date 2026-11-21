import cv2
import pytest

from visionaid.apps.inspect_data import video_metadata

pytestmark = pytest.mark.data


def test_video_opens(video_path):
    meta = video_metadata(video_path)
    assert meta["fps"] > 0
    assert meta["frame_count"] > 0


def test_refs_readable(ref_images):
    assert len(ref_images) >= 1
    assert all(img is not None and img.size > 0 for img in ref_images)


def test_inspect_app(video_path, tmp_path):
    from visionaid.apps import inspect_data

    rep = inspect_data.main(["--n", "3"])
    assert rep["video"]["rotation_deg"] in (0, 90, 180, 270)
    assert cv2.imread(str(next((video_path.parents[2] / "outputs" / "inspect").glob("*.jpg")))) is not None
