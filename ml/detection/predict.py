"""Step 7: run the trained model on any photo; save a picture with boxes and the contract-B JSON.

    python -m ml.detection.predict data/private/company-dataset/cab1_full_front.jpg \
        --weights runs/rfdetr-small-v1/checkpoint_best_total.pth --out runs/predictions
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from ml.detection.boxes import save_json

COLOURS = {"power_supply": "#1f5eff", "mcb": "#cf222e", "io_module": "#1a7f37"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("photos", nargs="+", type=Path)
    ap.add_argument("--weights", type=Path, required=True)
    ap.add_argument("--size", default="small")
    ap.add_argument("--threshold", type=float, default=0.3)
    ap.add_argument("--out", type=Path, default=Path("runs/predictions"))
    a = ap.parse_args()

    from ml.interfaces import detections_to_contract
    from ml.detection.detector import RFDETRDetector
    det = RFDETRDetector(a.weights, a.size, a.threshold)
    a.out.mkdir(parents=True, exist_ok=True)
    for p in a.photos:
        img = Image.open(p).convert("RGB")
        dets = det.predict(img)
        draw = ImageDraw.Draw(img)
        for d in dets:
            draw.rectangle(d["bbox"], outline=COLOURS.get(d["class_name"], "orange"), width=6)
            draw.text((d["bbox"][0] + 6, d["bbox"][1] + 6), f'{d["class_name"]} {d["score"]:.2f}', fill="yellow")
        img.thumbnail((2048, 2048))
        img.save(a.out / f"{p.stem}_pred.jpg", quality=85)
        save_json(detections_to_contract(p, dets, f"rf-detr-{a.size}", a.weights), a.out / f"{p.stem}_observations.json")
        print(f"{p.name}: {len(dets)} parts -> {a.out / (p.stem + '_pred.jpg')}")


if __name__ == "__main__":
    main()
