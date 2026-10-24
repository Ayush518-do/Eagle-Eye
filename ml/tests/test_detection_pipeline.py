"""Tests for the training pipeline that run without a GPU, model weights or company data."""
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from ml.detection import boxes as B
from ml.detection.detector import tiled_predict
from ml.detection.evaluate import average_precision, match, score
from ml.detection.import_labels import convert, photo_name_from_url

ROOT = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------- boxes
def test_iou_and_nms():
    assert B.iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1
    assert B.iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0
    assert math.isclose(B.iou([0, 0, 10, 10], [5, 0, 15, 10]), 50 / 150)
    keep = B.nms([[0, 0, 10, 10], [1, 1, 10, 10], [50, 50, 60, 60]], [0.9, 0.8, 0.7])
    assert keep == [0, 2]


def test_tiles_cover_image_and_edges():
    tiles = B.make_tiles(4096, 3072, tile=1024, overlap=0.25)
    assert all(t.w == 1024 and t.h == 1024 for t in tiles)
    assert max(t.x + t.w for t in tiles) == 4096 and max(t.y + t.h for t in tiles) == 3072
    assert B.make_tiles(800, 600) == [B.Tile(0, 0, 800, 600)]


def test_clip_box_drops_slivers():
    t = B.Tile(0, 0, 100, 100)
    assert B.clip_box_to_tile([10, 10, 50, 50], t) == [10, 10, 50, 50]
    assert B.clip_box_to_tile([90, 10, 130, 50], t) is None          # only 25 % inside
    assert B.clip_box_to_tile([200, 200, 210, 210], t) is None


def test_label_studio_round_trip():
    r = B.to_label_studio_result([100, 200, 300, 260], "mcb", 1000, 500, 0.4)
    name, box = B.from_label_studio_result(r)
    assert name == "mcb" and [round(v, 6) for v in box] == [100, 200, 300, 260]


def test_classes_file():
    names = [c["name"] for c in B.load_classes()]
    assert names == ["power_supply", "mcb", "io_module"]
    assert all(c["prompts"] for c in B.load_classes())


# ------------------------------------------------------------- import labels
def _photo(path, size=(2000, 1500), colour=(120, 130, 140)):
    Image.new("RGB", size, colour).save(path)


def test_import_label_studio_export(tmp_path):
    _photo(tmp_path / "cab1_a.jpg")
    task = {"data": {"image": "/data/local-files/?d=company-dataset/cab1_a.jpg"},
            "annotations": [{"result": [B.to_label_studio_result([100, 100, 400, 300], "power_supply", 2000, 1500),
                                        B.to_label_studio_result([500, 500, 560, 700], "mcb", 2000, 1500)]}],
            "predictions": [{"result": [B.to_label_studio_result([0, 0, 50, 50], "mcb", 2000, 1500)]}]}
    empty = {"data": {"image": "/data/local-files/?d=company-dataset/cab1_b.jpg"}, "annotations": []}
    coco, problems = convert([task, empty], tmp_path)
    assert len(coco["images"]) == 1 and len(coco["annotations"]) == 2      # predictions ignored
    assert any("cab1_b.jpg" in p for p in problems)
    assert photo_name_from_url("/data/local-files/?d=company-dataset%2Fx%20y.jpg") == "x y.jpg"


# ------------------------------------------------------------- build dataset (end to end)
def test_build_dataset_end_to_end(tmp_path):
    photos = tmp_path / "photos"; photos.mkdir()
    for n in ("cab1_full_front", "cab1_lower_front_io", "cab2_full_front_3_columns"):
        _photo(photos / f"{n}.jpg", size=(3000, 2000))
    coco = B.coco_skeleton(B.load_classes())
    for i, n in enumerate(("cab1_full_front", "cab1_lower_front_io", "cab2_full_front_3_columns"), start=1):
        coco["images"].append({"id": i, "file_name": f"{n}.jpg", "width": 3000, "height": 2000})
        coco["annotations"].append({"id": i, "image_id": i, "category_id": 3 if i > 1 else 1,
                                    "bbox": [200, 200, 300, 400], "area": 120000, "iscrowd": 0})
    B.save_json(coco, tmp_path / "labels.json")
    (tmp_path / "splits.yaml").write_text(
        "train: [cab1_full_front]\nvalid: [cab1_lower_front_io]\ntest: [cab2_full_front_3_columns]\n")
    # a public dataset whose class names are spelled differently, with test images that must be ignored
    for split in ("train", "valid", "test"):
        d = tmp_path / "external" / "breakers" / split; d.mkdir(parents=True)
        _photo(d / "p1.jpg", size=(640, 640))
        B.save_json({"images": [{"id": 1, "file_name": "p1.jpg", "width": 640, "height": 640}],
                     "categories": [{"id": 0, "name": "breakers", "supercategory": "none"},
                                    {"id": 1, "name": "2-Pole-Circuit-Breaker", "supercategory": "breakers"}],
                     "annotations": [{"id": 1, "image_id": 1, "category_id": 1, "bbox": [10, 10, 50, 100]}]},
                    d / "_annotations.coco.json")
    (tmp_path / "map.yaml").write_text("breakers:\n  2 pole circuit breaker: mcb\n")
    out = tmp_path / "ds"
    r = subprocess.run([sys.executable, "-m", "ml.detection.build_dataset", "--labels", str(tmp_path / "labels.json"),
                        "--photos", str(photos), "--splits", str(tmp_path / "splits.yaml"), "--out", str(out),
                        "--public-dir", str(tmp_path / "external"), "--public-map", str(tmp_path / "map.yaml")],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr + r.stdout
    info = json.loads((out / "dataset_info.json").read_text())
    assert info["train"]["boxes_per_class"]["power_supply"] >= 1
    assert info["train"]["boxes_per_class"]["mcb"] == 1                     # public, mapped despite spelling
    assert "public:breakers" not in info["test"]["sources"]                 # public never in test
    assert info["test_full"]["images"] == 1
    train_names = {i["file_name"] for i in B.load_json(out / "train" / "_annotations.coco.json")["images"]}
    assert not any("cab2" in n or "lower_front" in n for n in train_names)  # no leakage between splits
    for split in ("train", "valid", "test"):
        c = B.load_json(out / split / "_annotations.coco.json")
        for im in c["images"]:
            assert (out / split / im["file_name"]).exists()


def test_build_dataset_rejects_photo_in_two_splits(tmp_path):
    (tmp_path / "splits.yaml").write_text("train: [a]\nvalid: [a]\n")
    B.save_json(B.coco_skeleton(B.load_classes()), tmp_path / "l.json")
    r = subprocess.run([sys.executable, "-m", "ml.detection.build_dataset", "--labels", str(tmp_path / "l.json"),
                        "--photos", str(tmp_path), "--splits", str(tmp_path / "splits.yaml"), "--out", str(tmp_path / "o")],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode != 0 and "two splits" in (r.stderr + r.stdout)


# ------------------------------------------------------------- tiled detection
def test_tiled_predict_maps_tiles_back_and_merges():
    img = Image.new("RGB", (3000, 2000))
    def fake(tile_img):
        # pretend every tile sees one part at its top-left corner
        return [([10, 10, 60, 60], 0.9, "mcb")]
    dets = tiled_predict(img, fake, tile=1024)
    assert all(d["class_name"] == "mcb" for d in dets)
    assert any(d["bbox"][:2] == [10, 10] for d in dets)                     # first tile, full-image coords
    assert any(d["bbox"][0] > 1000 for d in dets)                           # later tiles shifted correctly


# ------------------------------------------------------------- evaluation maths
def test_average_precision_perfect_and_half():
    assert average_precision([(0.9, True), (0.8, True)], 2) == 1.0
    assert math.isclose(average_precision([(0.9, True), (0.8, False)], 2), 0.5)
    assert math.isnan(average_precision([], 0))


def test_score_reports_no_test_data_instead_of_a_number():
    coco = {"categories": [{"id": 1, "name": "power_supply"}, {"id": 3, "name": "io_module"}],
            "images": [{"id": 1, "file_name": "a.jpg"}],
            "annotations": [{"image_id": 1, "category_id": 3, "bbox": [0, 0, 100, 100]}]}
    preds = {"a.jpg": [{"bbox": [0, 0, 100, 100], "score": 0.9, "class_name": "io_module"},
                       {"bbox": [500, 500, 600, 600], "score": 0.8, "class_name": "power_supply"}]}
    r = score(preds, coco, threshold=0.3)
    assert r["io_module"] == {"truth_boxes": 1, "precision": 1.0, "recall": 1.0, "AP50": 1.0}
    assert r["power_supply"]["note"] == "no test data for this class"
    assert r["power_supply"]["false_alarms_at_threshold"] == 1
    assert match([{"bbox": [0, 0, 10, 10], "score": 1}], [[50, 50, 60, 60]]) == [(1, False)]


# ------------------------------------------------------------- interface
def test_detect_components_refuses_without_weights(monkeypatch):
    from ml.interfaces import ModelUnavailableError, detect_components
    monkeypatch.delenv("DETECTOR_WEIGHTS_PATH", raising=False)
    with pytest.raises(ModelUnavailableError, match="DETECTOR_WEIGHTS_PATH"):
        detect_components("x.jpg")
    monkeypatch.setenv("DETECTOR_WEIGHTS_PATH", "missing.pth")
    with pytest.raises(ModelUnavailableError, match="not found"):
        detect_components("x.jpg")


def test_detections_to_contract(tmp_path):
    from ml.interfaces import detections_to_contract
    _photo(tmp_path / "p.jpg", size=(400, 300))
    c = detections_to_contract(tmp_path / "p.jpg", [{"bbox": [1, 2, 30, 40], "score": 0.77, "class_name": "mcb"}], "rf-detr-small")
    o = c["observations"][0]
    assert c["image_size"] == [400, 300] and o["source"] == "detector" and o["kind"] == "component"
    assert o["class_name"] == "mcb" and o["confidence"] == 0.77
