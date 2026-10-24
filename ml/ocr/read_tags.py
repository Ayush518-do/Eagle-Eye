"""Find and read text in a cabinet photo with RapidOCR, returning contract B observations.

Usage:
    python -m ml.ocr.read_tags data/private/photo1.jpg --expected CB11 CB12 PS11

Each reading keeps its raw text; when an expected tag list is given, `text` is the matched tag
and the raw reading is kept in `raw_text`, so any correction is visible.
"""
import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable, Optional

from PIL import Image

from ml.interfaces import ModelUnavailableError
from ml.ocr.tag_matcher import match_tag

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise ModelUnavailableError("RapidOCR is not installed: pip install -r ml/requirements-ocr.txt") from exc
        _engine = RapidOCR()
    return _engine


def read_tags(image_path: str, expected: Optional[Iterable[str]] = None, image_id: Optional[str] = None) -> dict:
    path = Path(image_path)
    with Image.open(path) as im:
        size = (im.width, im.height)
    result, _ = _get_engine()(str(path))
    expected = list(expected or [])
    observations = []
    for i, (points, text, score) in enumerate(result or [], start=1):
        xs = [p[0] for p in points]; ys = [p[1] for p in points]
        matched = match_tag(text, expected) if expected else None
        observations.append({
            "observation_id": f"OCR-{i:03d}",
            "source": "ocr",
            "kind": "tag_label",
            "class_name": "tag_label",
            "bbox": [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))],
            "confidence": None,
            "text": (matched.tag if matched and matched.tag else text),
            "raw_text": text,
            "text_confidence": float(score),
            "model": {"name": "rapidocr-onnxruntime", "version": None, "weights_sha256": None},
        })
    return {
        "contract_version": "0.1",
        "image_id": image_id or path.stem,
        "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "image_size": list(size),
        "observations": observations,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--expected", nargs="*")
    a = ap.parse_args()
    print(json.dumps(read_tags(a.image, a.expected), indent=2))
