"""Shared entry points between the ML parts and the backend.

Return formats are defined in docs/contracts.md. The backend calls only these
functions, so models can change without touching backend code.
"""
from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path


class ModelUnavailableError(RuntimeError):
    """Raised when a model or its weights are not configured.

    Callers must show this message to the user; never replace it with made-up output.
    """


def parse_drawing(pdf_path: str) -> dict:
    """Drawing PDF -> contract A (expected items, plus BOM, BOM checks and arrangement groups).

    Needs a PDF with a text layer (exported from CAD). A scanned drawing has none: then it raises
    ModelUnavailableError so the parts list can be typed in by hand instead.
    """
    try:
        from ml.drawing.parse_drawing import to_contract
    except ImportError as exc:
        raise ModelUnavailableError(f"Drawing parser packages not installed ({exc}): pip install -r ml/requirements-ocr.txt") from exc
    result = to_contract(Path(pdf_path))
    if not result["items"]:
        raise ModelUnavailableError("No component tags found in the drawing (no text layer?). Enter the parts list by hand.")
    return result


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def detections_to_contract(image_path, dets: list[dict], model_name: str, weights=None, source: str = "detector") -> dict:
    """Turn [{'bbox','score','class_name'}] into contract B (kind='component')."""
    from PIL import Image
    image_path = Path(image_path)
    with Image.open(image_path) as im:
        size = [im.width, im.height]
    return {
        "contract_version": "0.3",
        "image_id": image_path.stem,
        "image_sha256": _sha256(image_path),
        "image_size": size,
        "observations": [
            {
                "observation_id": f"DET-{i:03d}",
                "source": source,
                "kind": "component",
                "class_name": d["class_name"],
                "bbox": [round(v, 1) for v in d["bbox"]],
                "confidence": round(d["score"], 4),
                "text": None, "raw_text": None, "text_confidence": None,
                "model": {"name": model_name, "version": Path(weights).name if weights else None,
                          "weights_sha256": _sha256(Path(weights)) if weights else None},
            }
            for i, d in enumerate(sorted(dets, key=lambda d: -d["score"]), start=1)
        ],
    }


@lru_cache(maxsize=1)
def _load_detector(weights: str, size: str, threshold: float):
    from ml.detection.detector import RFDETRDetector
    return RFDETRDetector(weights, size, threshold)


@lru_cache(maxsize=1)
def _load_zero_shot(threshold: float):
    from ml.detection.zero_shot import OWLv2Detector
    return OWLv2Detector(threshold=threshold)


def detect_components(image_path: str) -> dict:
    """Cabinet photo -> contract B with kind='component', from every configured source:

      source "detector"   RF-DETR fine-tuned on public data (mcb)      .env: DETECTOR_WEIGHTS_PATH=...
      source "zero_shot"  OWLv2, pretrained, from text prompts (all)   .env: ZERO_SHOT_ENABLED=true

    Optional: DETECTOR_MODEL_SIZE=small, DETECTOR_THRESHOLD=0.3, ZERO_SHOT_THRESHOLD=0.15.
    Each observation keeps its own source; the engine merges them (evidence fusion).
    """
    from PIL import Image
    weights = os.environ.get("DETECTOR_WEIGHTS_PATH", "")
    zero_shot = os.environ.get("ZERO_SHOT_ENABLED", "").lower() in {"1", "true", "yes"}
    if not weights and not zero_shot:
        raise ModelUnavailableError(
            "No detector configured: set DETECTOR_WEIGHTS_PATH and/or ZERO_SHOT_ENABLED=true.")
    if weights and not Path(weights).is_file():
        raise ModelUnavailableError(f"Detector weights not found: {weights}")

    image = Image.open(image_path).convert("RGB")
    size = os.environ.get("DETECTOR_MODEL_SIZE", "small")
    result = None
    try:
        if weights:
            det = _load_detector(weights, size, float(os.environ.get("DETECTOR_THRESHOLD", "0.3")))
            result = detections_to_contract(image_path, det.predict(image), f"rf-detr-{size}", weights, "detector")
        if zero_shot:
            zs = _load_zero_shot(float(os.environ.get("ZERO_SHOT_THRESHOLD", "0.15")))
            extra = detections_to_contract(image_path, zs.predict(image), "owlv2-base-patch16-ensemble", None, "zero_shot")
            for o in extra["observations"]:
                o["observation_id"] = o["observation_id"].replace("DET-", "ZS-")
            if result is None:
                result = extra
            else:
                result["observations"] += extra["observations"]
    except ImportError as exc:
        raise ModelUnavailableError(f"Detector packages not installed ({exc}). See ml/detection/README.md.") from exc
    return result


def read_tags(image_path: str, expected_tags: list[str] | None = None) -> dict:
    """Cabinet photo -> contract B with kind='tag_label' (stickers) and kind='rating_text' (e.g. "16 A").

    Pass the drawing's tags as `expected_tags` so look-alike OCR mistakes ("C811") are corrected to a
    known tag ("CB11"); the raw reading stays in `raw_text`. Coordinates are in the upright photo.
    """
    try:
        from ml.ocr.read_tags import OCRUnavailableError, read_tags as _read_tags
    except ImportError as exc:
        raise ModelUnavailableError(f"OCR packages not installed ({exc}): pip install -r ml/requirements-ocr.txt") from exc
    try:
        return _read_tags(image_path, expected_tags, with_ratings=True)
    except OCRUnavailableError as exc:
        raise ModelUnavailableError(str(exc)) from exc
