"""Run a trained RF-DETR model on a full-size photo, tile by tile.

The model sees 512 px inputs. A 4096 px photo shrunk to 512 px loses small parts, so we run it on
overlapping 1024 px tiles plus one shrunk copy of the whole photo, then merge duplicate boxes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PIL import Image

from ml.detection.boxes import make_tiles, merge_tile_detections

SIZES = {"nano": "RFDETRNano", "small": "RFDETRSmall", "medium": "RFDETRMedium"}

# (pil_image) -> list of (xyxy box in that image, score, class_name)
PredictFn = Callable[[Image.Image], list]


def tiled_predict(image: Image.Image, predict_fn: PredictFn, tile: int = 1024) -> list[dict]:
    dets = []
    for t in make_tiles(image.width, image.height, tile=tile):
        for box, score, name in predict_fn(image.crop(tuple(t.box))):
            dets.append({"bbox": [box[0] + t.x, box[1] + t.y, box[2] + t.x, box[3] + t.y],
                         "score": float(score), "class_name": name})
    scale = tile / max(image.size)
    if scale < 1:
        small = image.resize((round(image.width * scale), round(image.height * scale)))
        for box, score, name in predict_fn(small):
            dets.append({"bbox": [v / scale for v in box], "score": float(score), "class_name": name})
    return merge_tile_detections(dets)


class RFDETRDetector:
    def __init__(self, weights: str | Path, size: str = "small", threshold: float = 0.3):
        import rfdetr
        cls = getattr(rfdetr, SIZES[size])
        self.model = cls(pretrain_weights=str(weights))
        self.threshold = threshold
        self.names = list(self.model.class_names)

    def _predict(self, img: Image.Image) -> list:
        d = self.model.predict(img, threshold=self.threshold)
        return [(box.tolist(), float(s), self.names[int(c)] if int(c) < len(self.names) else str(int(c)))
                for box, s, c in zip(d.xyxy, d.confidence, d.class_id)]

    def predict(self, image: Image.Image, tile: int = 1024) -> list[dict]:
        return tiled_predict(image.convert("RGB"), self._predict, tile)
