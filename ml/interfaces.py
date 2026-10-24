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
    """Drawing PDF -> contract A (expected items)."""
    raise ModelUnavailableError("Drawing parser not implemented yet (ML drawing/OCR branch).")


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


def detect_components(image_path: str) -> dict:
    """Cabinet photo -> contract B with kind='component', using the trained RF-DETR model.

    Configure in .env:  DETECTOR_WEIGHTS_PATH=runs/rfdetr-small-v1/checkpoint_best_total.pth
                        DETECTOR_MODEL_SIZE=small   DETECTOR_THRESHOLD=0.3
    """
    weights = os.environ.get("DETECTOR_WEIGHTS_PATH", "")
    if not weights:
        raise ModelUnavailableError("DETECTOR_WEIGHTS_PATH is not set: no trained detector configured.")
    if not Path(weights).is_file():
        raise ModelUnavailableError(f"Detector weights not found: {weights}")
    try:
        det = _load_detector(weights, os.environ.get("DETECTOR_MODEL_SIZE", "small"),
                             float(os.environ.get("DETECTOR_THRESHOLD", "0.3")))
    except ImportError as exc:
        raise ModelUnavailableError(f"Detector packages not installed ({exc}). See ml/detection/README.md.") from exc
    from PIL import Image
    dets = det.predict(Image.open(image_path))
    return detections_to_contract(image_path, dets, f"rf-detr-{os.environ.get('DETECTOR_MODEL_SIZE', 'small')}", weights)


def read_tags(image_path: str) -> dict:
    """Cabinet photo -> contract B with kind='tag_label'."""
    raise ModelUnavailableError("Tag reader not implemented yet (ML drawing/OCR branch).")
