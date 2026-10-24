"""Step 6: run every available model on the company photos and save their boxes per source.

    python -m ml.detection.predict_all data/private/rfdetr_dataset/test_full \
        --weights runs/rfdetr-mcb-v1/checkpoint_best_total.pth --zero-shot --out runs/eval/test

Writes  <out>/detector/<photo>.json     RF-DETR boxes (contract B, source "detector")
        <out>/zero_shot/<photo>.json    OWLv2 boxes   (contract B, source "zero_shot")
        <out>/previews/<photo>_<source>.jpg
Low thresholds on purpose, so evaluate.py can measure every confidence level; the app uses its own
threshold later.
"""
import argparse
from pathlib import Path

from PIL import Image

from ml.detection.boxes import save_json
from ml.detection.prelabel_owlv2 import draw_preview
from ml.interfaces import detections_to_contract


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("photos", type=Path, help="folder of photos (e.g. rfdetr_dataset/test_full)")
    ap.add_argument("--weights", type=Path, help="trained RF-DETR weights (skip to run OWLv2 only)")
    ap.add_argument("--size", default="small")
    ap.add_argument("--zero-shot", action="store_true", help="also run OWLv2")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if not a.weights and not a.zero_shot:
        raise SystemExit("Nothing to run: give --weights and/or --zero-shot.")

    models = {}
    if a.weights:
        from ml.detection.detector import RFDETRDetector
        models["detector"] = (RFDETRDetector(a.weights, a.size, threshold=0.05), f"rf-detr-{a.size}", a.weights)
    if a.zero_shot:
        from ml.detection.zero_shot import OWLv2Detector
        models["zero_shot"] = (OWLv2Detector(threshold=0.05), "owlv2-base-patch16-ensemble", None)

    photos = sorted(p for p in a.photos.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    for p in photos:
        img = Image.open(p).convert("RGB")
        for source, (model, name, weights) in models.items():
            dets = model.predict(img)
            save_json(detections_to_contract(p, dets, name, weights, source=source), a.out / source / f"{p.stem}.json")
            draw_preview(img, [d for d in dets if d["score"] >= 0.3], a.out / "previews" / f"{p.stem}_{source}.jpg")
            print(f"{p.name} [{source}]: {sum(d['score'] >= 0.3 for d in dets)} boxes at score >= 0.3")


if __name__ == "__main__":
    main()
