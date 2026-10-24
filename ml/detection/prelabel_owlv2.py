"""Step 1: OWLv2 first-guess boxes for labelling the company photos (the test answer key).

    python -m ml.detection.prelabel_owlv2 data/private/company-dataset --out data/private/prelabels

OWLv2 is a pretrained model that finds objects from a text description ("a miniature circuit breaker"),
with no training. Its boxes are loaded into Label Studio as suggestions; a person corrects them.

Writes into --out:
  previews/<photo>.jpg          the photo with OWLv2's boxes drawn on
  label_studio_tasks.json       import this into Label Studio (boxes appear as suggestions)
  owlv2_detections.json         raw boxes, for the record

Tuning rule: change prompts/threshold only while looking at the DEV photos' previews (splits.yaml).
Looking at test photos while tuning makes their final score optimistic.
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from ml.detection.boxes import save_json, to_label_studio_result
from ml.detection.zero_shot import MODEL_ID, OWLv2Detector

COLOURS = {"power_supply": "#1f5eff", "mcb": "#cf222e", "io_module": "#1a7f37"}


def draw_preview(img: Image.Image, dets: list[dict], path: Path) -> None:
    prev = img.copy()
    draw = ImageDraw.Draw(prev)
    for d in dets:
        draw.rectangle(d["bbox"], outline=COLOURS.get(d["class_name"], "orange"), width=6)
        draw.text((d["bbox"][0] + 6, d["bbox"][1] + 6), f'{d["class_name"]} {d["score"]:.2f}', fill="yellow")
    path.parent.mkdir(parents=True, exist_ok=True)
    prev.thumbnail((2048, 2048))
    prev.save(path, quality=85)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("photos", type=Path)
    ap.add_argument("--out", type=Path, default=Path("data/private/prelabels"))
    ap.add_argument("--threshold", type=float, default=0.15, help="lower = more boxes (and more wrong ones)")
    ap.add_argument("--only", nargs="*", help="photo names (without .jpg) to process, e.g. the dev photos")
    ap.add_argument("--url-prefix", default="/data/local-files/?d=company-dataset/",
                    help="how Label Studio finds the photos (see README step 2)")
    args = ap.parse_args()

    det = OWLv2Detector(threshold=args.threshold)
    tasks, raw = [], {}
    photos = sorted(p for p in args.photos.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if args.only:
        photos = [p for p in photos if p.stem in set(args.only)]
    for photo in photos:
        img = Image.open(photo).convert("RGB")
        dets = det.predict(img)
        raw[photo.name] = dets
        draw_preview(img, dets, args.out / "previews" / f"{photo.stem}.jpg")
        tasks.append({
            "data": {"image": args.url_prefix + photo.name},
            "predictions": [{"model_version": "owlv2-zero-shot",
                             "result": [to_label_studio_result(d["bbox"], d["class_name"], img.width, img.height, d["score"])
                                        for d in dets]}],
        })
        counts = {n: sum(d["class_name"] == n for d in dets) for n in COLOURS}
        print(f"{photo.name}: {len(dets)} boxes {counts}")

    save_json(tasks, args.out / "label_studio_tasks.json")
    save_json({"model": MODEL_ID, "threshold": args.threshold, "detections": raw}, args.out / "owlv2_detections.json")
    print(f"\nPreviews: {args.out / 'previews'}")
    print(f"Label Studio import file: {args.out / 'label_studio_tasks.json'}")


if __name__ == "__main__":
    main()
