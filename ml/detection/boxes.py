"""Box, tile and label-format helpers shared by every detection script.

Everything here is plain Python + numpy (no torch), so it is fast to test.
Boxes are always [x_min, y_min, x_max, y_max] in pixels unless a name says otherwise.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

CLASSES_FILE = Path(__file__).with_name("classes.yaml")


def load_classes(path: Path = CLASSES_FILE) -> list[dict]:
    """[{'id': 1, 'name': 'power_supply', 'prompts': [...]}, ...] sorted by id."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return sorted(data["classes"], key=lambda c: c["id"])


# ---------------------------------------------------------------- geometry
def iou(a, b) -> float:
    """Intersection over union: overlap area / combined area. 1 = identical, 0 = no overlap."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def nms(boxes, scores, iou_threshold: float = 0.5) -> list[int]:
    """Non-maximum suppression: when boxes overlap a lot, keep only the highest-scoring one.
    Returns the indexes of the boxes to keep."""
    order = list(np.argsort(scores)[::-1])
    keep = []
    while order:
        i = order.pop(0)
        keep.append(int(i))
        order = [j for j in order if iou(boxes[i], boxes[j]) < iou_threshold]
    return keep


@dataclass
class Tile:
    x: int          # left edge in the full image
    y: int          # top edge in the full image
    w: int
    h: int

    @property
    def box(self):
        return [self.x, self.y, self.x + self.w, self.y + self.h]


def make_tiles(width: int, height: int, tile: int = 1024, overlap: float = 0.25) -> list[Tile]:
    """Cover the image with square tiles that overlap, so no part is only ever seen cut in half.
    Edge tiles are shifted inwards instead of being smaller."""
    if width <= tile and height <= tile:
        return [Tile(0, 0, width, height)]
    step = max(1, int(tile * (1 - overlap)))

    def starts(total):
        if total <= tile:
            return [0]
        s = list(range(0, total - tile + 1, step))
        if s[-1] != total - tile:
            s.append(total - tile)
        return s

    return [Tile(x, y, min(tile, width), min(tile, height)) for y in starts(height) for x in starts(width)]


def clip_box_to_tile(box, t: Tile, min_visible: float = 0.6):
    """Return the box in tile coordinates, or None if less than `min_visible` of it is inside the tile.
    A part cut to a sliver would teach the model wrong shapes, so we drop it."""
    x1, y1 = max(box[0], t.x), max(box[1], t.y)
    x2, y2 = min(box[2], t.x + t.w), min(box[3], t.y + t.h)
    if x2 <= x1 or y2 <= y1:
        return None
    full = (box[2] - box[0]) * (box[3] - box[1])
    if full <= 0 or (x2 - x1) * (y2 - y1) / full < min_visible:
        return None
    return [x1 - t.x, y1 - t.y, x2 - t.x, y2 - t.y]


def merge_tile_detections(dets: list[dict], iou_threshold: float = 0.5) -> list[dict]:
    """dets: [{'bbox': full-image box, 'score': float, 'class_name': str}, ...] from all tiles.
    The same part is often found in two overlapping tiles; keep the best box per class."""
    out = []
    for name in sorted({d["class_name"] for d in dets}):
        group = [d for d in dets if d["class_name"] == name]
        keep = nms([d["bbox"] for d in group], [d["score"] for d in group], iou_threshold)
        out += [group[i] for i in keep]
    return out


# ---------------------------------------------------------------- COCO
def coco_skeleton(classes: list[dict]) -> dict:
    return {
        "images": [],
        "annotations": [],
        "categories": [{"id": c["id"], "name": c["name"], "supercategory": "component"} for c in classes],
    }


def xyxy_to_coco(b):
    """COCO stores [x, y, width, height]."""
    return [round(b[0], 2), round(b[1], 2), round(b[2] - b[0], 2), round(b[3] - b[1], 2)]


def coco_to_xyxy(b):
    return [b[0], b[1], b[0] + b[2], b[1] + b[3]]


def save_json(obj, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- Label Studio
def to_label_studio_result(bbox, class_name: str, img_w: int, img_h: int, score: float | None = None) -> dict:
    """Label Studio stores boxes as percentages of the image size."""
    r = {
        "from_name": "label", "to_name": "image", "type": "rectanglelabels",
        "original_width": img_w, "original_height": img_h, "image_rotation": 0,
        "value": {
            "x": 100 * bbox[0] / img_w, "y": 100 * bbox[1] / img_h,
            "width": 100 * (bbox[2] - bbox[0]) / img_w, "height": 100 * (bbox[3] - bbox[1]) / img_h,
            "rotation": 0, "rectanglelabels": [class_name],
        },
    }
    if score is not None:
        r["score"] = float(score)
    return r


def from_label_studio_result(r: dict):
    """Inverse of to_label_studio_result: returns (class_name, [x1, y1, x2, y2] in pixels)."""
    v, w, h = r["value"], r["original_width"], r["original_height"]
    if v.get("rotation", 0) not in (0, 0.0):
        raise ValueError("Rotated boxes are not supported: please draw boxes without rotation.")
    x1, y1 = v["x"] * w / 100, v["y"] * h / 100
    return v["rectanglelabels"][0], [x1, y1, x1 + v["width"] * w / 100, y1 + v["height"] * h / 100]
