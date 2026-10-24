"""Step 1: OWLv2 zero-shot test + pre-labels (first-guess boxes for a person to correct).

    python -m ml.detection.prelabel_owlv2 data/private/company-dataset --out data/private/prelabels

OWLv2 is a pretrained model that finds objects from a text description ("a miniature circuit breaker"),
with no training. We use it twice:
  1. As a test: do its boxes look right on our photos? (see the preview images)
  2. As a labelling helper: its boxes are loaded into Label Studio, where a person fixes them.

Writes into --out:
  previews/<photo>.jpg          the photo with OWLv2's boxes drawn on
  label_studio_tasks.json       import this into Label Studio (boxes appear as suggestions)
  owlv2_detections.json         raw boxes, for the record
Photos are cut into overlapping tiles first, because small parts vanish when a 4096 px photo
is shrunk to the model's 960 px input.
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from ml.detection.boxes import load_classes, make_tiles, merge_tile_detections, save_json, to_label_studio_result

MODEL_ID = "google/owlv2-base-patch16-ensemble"   # Apache-2.0
COLOURS = {"power_supply": "#1f5eff", "mcb": "#cf222e", "io_module": "#1a7f37"}


def run_owlv2(image: Image.Image, prompts: list[str], model, processor, device, threshold: float):
    import torch
    inputs = processor(text=[prompts], images=image, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = model(**inputs)
    res = processor.post_process_grounded_object_detection(
        outputs, threshold=threshold, target_sizes=[(image.height, image.width)], text_labels=[prompts])[0]
    return [(b.tolist(), float(s), int(l)) for b, s, l in zip(res["boxes"], res["scores"], res["labels"])]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("photos", type=Path)
    ap.add_argument("--out", type=Path, default=Path("data/private/prelabels"))
    ap.add_argument("--threshold", type=float, default=0.15, help="lower = more boxes (and more wrong ones)")
    ap.add_argument("--tile", type=int, default=1536)
    ap.add_argument("--url-prefix", default="/data/local-files/?d=company-dataset/",
                    help="how Label Studio finds the photos (see README step 2)")
    args = ap.parse_args()

    import torch
    from transformers import Owlv2ForObjectDetection, Owlv2Processor
    device = "cuda" if torch.cuda.is_available() else "cpu"
    processor = Owlv2Processor.from_pretrained(MODEL_ID)
    model = Owlv2ForObjectDetection.from_pretrained(MODEL_ID).to(device).eval()

    classes = load_classes()
    prompts, prompt_class = [], []
    for c in classes:
        for p in c["prompts"]:
            prompts.append(p)
            prompt_class.append(c["name"])

    tasks, raw = [], {}
    photos = sorted(p for p in args.photos.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    for photo in photos:
        img = Image.open(photo).convert("RGB")
        dets = []
        for t in make_tiles(img.width, img.height, tile=args.tile):
            crop = img.crop(tuple(t.box))
            for box, score, label in run_owlv2(crop, prompts, model, processor, device, args.threshold):
                dets.append({"bbox": [box[0] + t.x, box[1] + t.y, box[2] + t.x, box[3] + t.y],
                             "score": score, "class_name": prompt_class[label]})
        dets = merge_tile_detections(dets)
        raw[photo.name] = dets

        prev = img.copy()
        draw = ImageDraw.Draw(prev)
        for d in dets:
            draw.rectangle(d["bbox"], outline=COLOURS.get(d["class_name"], "orange"), width=6)
            draw.text((d["bbox"][0] + 6, d["bbox"][1] + 6), f'{d["class_name"]} {d["score"]:.2f}', fill="yellow")
        (args.out / "previews").mkdir(parents=True, exist_ok=True)
        prev.thumbnail((2048, 2048))
        prev.save(args.out / "previews" / f"{photo.stem}.jpg", quality=85)

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
    print(f"\nPreviews: {args.out / 'previews'}  <- open these and judge the boxes by eye")
    print(f"Label Studio import file: {args.out / 'label_studio_tasks.json'}")


if __name__ == "__main__":
    main()
