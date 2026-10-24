"""Read the tag stickers (CB11, PS12, DS1 …) in a cabinet photo with RapidOCR -> contract B observations.

    python -m ml.ocr.read_tags data/private/company-dataset/cab1_power_supplies_closeup.jpg \
        --expected-json data/private/expected_items.json --out data/private/ocr/ps_closeup.json

How it works, and why:
  * The photo is turned upright first (phones store rotation separately, as EXIF metadata).
  * It is read in overlapping 1280 px tiles: stickers are only ~60 px tall in a 4096 px photo and
    vanish if the whole photo is shrunk to the reader's input size.
  * Each tile is read twice, as-is and turned 90°, because breaker stickers are printed sideways.
  * Only readings that are a tag ON THEIR OWN count. Wire sleeves are printed with text like
    "CB11-4/PS11-N": that mentions CB11 but doesn't show the breaker is there, so it's ignored.
  * With an expected tag list, look-alike OCR mistakes are corrected ("C811" -> "CB11") and the raw
    reading is kept in `raw_text`, so every correction is visible.
  * The same sticker read in several tiles/orientations is merged into one observation.

Coordinates are pixels of the upright photo, [x_min, y_min, x_max, y_max].
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable, Optional

from PIL import Image, ImageOps

from ml.ocr.tag_matcher import match_tag

ENGINE_NAME = "rapidocr-onnxruntime"
STANDALONE = re.compile(r"^[A-Z]{1,5}[0-9]{1,3}$")        # a tag alone: "CB11", "RCCB1", "PS22"
_engine = None


class OCRUnavailableError(RuntimeError):
    pass


def _get_engine():
    global _engine
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise OCRUnavailableError("RapidOCR is not installed: pip install -r ml/requirements-ocr.txt") from exc
        _engine = RapidOCR()
    return _engine


def _tiles(w: int, h: int, tile: int, overlap: float):
    if w <= tile and h <= tile:
        return [(0, 0, w, h)]
    step = max(1, int(tile * (1 - overlap)))

    def starts(n):
        s = list(range(0, max(1, n - tile + 1), step))
        if s[-1] != max(0, n - tile):
            s.append(max(0, n - tile))
        return s
    return [(x, y, min(x + tile, w), min(y + tile, h)) for y in starts(h) for x in starts(w)]


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def clean(text: str) -> str:
    return "".join(ch for ch in text.upper() if ch.isalnum())


def is_standalone_tag(raw: str) -> bool:
    """'CB11' yes; 'CB11-4/PS11-N' (wire sleeve) no; 'A9N2P16CIN' (part number) no."""
    if any(ch in raw for ch in "/-()+:,."):
        return False
    return bool(STANDALONE.match(clean(raw)))


def read_raw(image: Image.Image, tile: int = 1280, overlap: float = 0.25, rotations=(0, 90)) -> list[dict]:
    """Every text line the engine reads, in upright-photo coordinates."""
    import numpy as np
    eng = _get_engine()
    out = []
    for x0, y0, x1, y1 in _tiles(image.width, image.height, tile, overlap):
        crop = image.crop((x0, y0, x1, y1))
        cw = crop.width
        for rot in rotations:
            im = crop.rotate(rot, expand=True) if rot else crop     # 90 = turned counter-clockwise
            res, _ = eng(np.array(im))
            for pts, text, score in res or []:
                if rot == 90:      # undo the turn: rotated (u, v) -> crop (cw - 1 - v, u)
                    pts = [(cw - 1 - v, u) for u, v in pts]
                xs = [p[0] + x0 for p in pts]
                ys = [p[1] + y0 for p in pts]
                out.append({"text": text, "score": 0.0 if score is None else float(score),
                            "rotation": rot, "bbox": [min(xs), min(ys), max(xs), max(ys)]})
    return out


def merge_duplicates(obs: list[dict], iou_threshold: float = 0.3) -> list[dict]:
    """The same sticker read twice (overlapping tiles, both orientations): keep the best reading."""
    kept: list[dict] = []
    for o in sorted(obs, key=lambda o: -o["score"]):
        if not any(k["tag"] == o["tag"] and _iou(k["bbox"], o["bbox"]) > iou_threshold for k in kept):
            kept.append(o)
    # A cut-off read of the same sticker ("DS2" where "DS21" was read at the same spot): keep the longer tag.
    return [o for o in kept
            if not any(k is not o and k["tag"] != o["tag"] and k["tag"].startswith(o["tag"])
                       and _iou(k["bbox"], o["bbox"]) > 0.5 for k in kept)]


def find_tags(image: Image.Image, expected: Optional[Iterable[str]] = None, raw: Optional[list] = None,
              **kw) -> list[dict]:
    """Tag stickers in the photo. Pass `raw` (from read_raw) to avoid reading the photo twice."""
    expected = [clean(t) for t in (expected or [])]
    found = []
    for r in (raw if raw is not None else read_raw(image, **kw)):
        if not is_standalone_tag(r["text"]):
            continue
        raw = clean(r["text"])
        tag = raw
        if expected:
            m = match_tag(raw, expected)
            # one-character corrections only when the lengths agree (avoids 'S1' -> 'DS1')
            if not m.tag or (m.distance > 0 and len(m.tag) != len(raw)):
                continue
            tag = m.tag
        found.append({**r, "tag": tag, "raw": r["text"]})
    return merge_duplicates(found)


def read_tags(image_path: str, expected: Optional[Iterable[str]] = None, image_id: Optional[str] = None,
              **kw) -> dict:
    """Contract B (kind='tag_label') for one photo."""
    path = Path(image_path)
    image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    tags = find_tags(image, expected, **kw)
    return {
        "contract_version": "0.2",
        "image_id": image_id or path.stem,
        "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "image_size": [image.width, image.height],
        "observations": [
            {
                "observation_id": f"OCR-{i:03d}",
                "source": "ocr",
                "kind": "tag_label",
                "class_name": "tag_label",
                "bbox": [round(v, 1) for v in t["bbox"]],
                "confidence": None,
                "text": t["tag"],
                "raw_text": t["raw"],
                "text_confidence": round(t["score"], 4),
                "model": {"name": ENGINE_NAME, "version": None, "weights_sha256": None},
            }
            for i, t in enumerate(sorted(tags, key=lambda t: (t["bbox"][1], t["bbox"][0])), start=1)
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--expected", nargs="*", help="expected tags, e.g. CB11 CB12")
    ap.add_argument("--expected-json", type=Path, help="contract A file from ml.drawing.parse_drawing")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    expected = list(a.expected or [])
    if a.expected_json:
        expected += [it["tag"] for it in json.loads(a.expected_json.read_text(encoding="utf-8"))["items"]]
    result = read_tags(a.image, expected or None)
    tags = sorted({o["text"] for o in result["observations"]})
    corrected = [f'{o["raw_text"]}->{o["text"]}' for o in result["observations"] if clean(o["raw_text"]) != o["text"]]
    print(f"{Path(a.image).name}: {len(tags)} tags read: {' '.join(tags)}")
    if corrected:
        print("  look-alike corrections:", ", ".join(corrected))
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
