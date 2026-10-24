import json

import pytest
from PIL import Image

from ml.detection.inspect_dataset import inspect
from ml.detection.split import split
from ml.detection.strip_metadata import strip


def _img(path, color=(10, 20, 30)):
    Image.new("RGB", (40, 30), color).save(path)


def test_inspect_counts_duplicates_corrupt_and_labels(tmp_path):
    _img(tmp_path / "a.png"); _img(tmp_path / "b.png"); _img(tmp_path / "c.png", (200, 0, 0))
    (tmp_path / "bad.jpg").write_bytes(b"not an image")
    coco = tmp_path / "labels.json"
    coco.write_text(json.dumps({
        "images": [{"id": 1}, {"id": 2}],
        "categories": [{"id": 0, "name": "mcb"}],
        "annotations": [{"image_id": 1, "category_id": 0}, {"image_id": 1, "category_id": 0}],
    }))
    r = inspect(tmp_path, coco)
    assert r["image_count"] == 4
    assert len(r["exact_duplicates"]) == 1          # a.png and b.png are identical
    assert len(r["corrupt"]) == 1
    assert r["labels"]["per_class"] == {"mcb": 2}
    assert r["labels"]["images_without_labels"] == 1


def test_split_keeps_groups_together():
    rows = [{"image": "1.jpg", "group": "A"}, {"image": "2.jpg", "group": "A"}, {"image": "5.jpg", "group": "B"}]
    s = split(rows, {"B"})
    assert s["train"] == ["1.jpg", "2.jpg"] and s["test"] == ["5.jpg"]


def test_split_refuses_no_training_or_test_group():
    rows = [{"image": "1.jpg", "group": "A"}]
    with pytest.raises(ValueError):
        split(rows, {"A"})
    with pytest.raises(ValueError):
        split(rows, {"Z"})


def test_strip_removes_exif_and_never_overwrites(tmp_path):
    src = tmp_path / "in.jpg"
    exif = Image.Exif(); exif[0x0110] = "SecretCam"   # camera model tag
    Image.new("RGB", (20, 20), (1, 2, 3)).save(src, exif=exif)
    out = strip(src, tmp_path / "clean")
    with Image.open(out) as im:
        assert len(im.getexif()) == 0
    with pytest.raises(FileExistsError):
        strip(src, tmp_path / "clean")
