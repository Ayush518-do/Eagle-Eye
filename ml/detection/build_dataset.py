"""Step 4: build the dataset: public images to TRAIN the detector, company photos to TEST it.

    python -m ml.detection.build_dataset --labels data/private/labels/company_coco.json \
        --photos data/private/company-dataset --splits ml/detection/splits.yaml \
        --public-map ml/detection/public_class_map.yaml --out data/private/rfdetr_dataset

Output:
    rfdetr_dataset/
      train/  valid/      public images, only the classes with `detector: true` in classes.yaml
      test/               tiles of the company test photos (all classes), for RF-DETR's own report
      test_full/          full-size company TEST photos + all their labels   -> evaluate.py (final scores)
      dev_full/           full-size company DEV photos + labels               -> tune prompts/thresholds here
      dataset_info.json   which image went where, boxes per class, source of every image

Rules that keep the evaluation honest:
  * company photos never go into train/valid (unless you list them there on purpose in splits.yaml);
  * public images never go into test;
  * a photo goes to exactly one split; every image name carries its source ("co-", "pub-<name>-").
"""
import argparse
import hashlib
import random
import shutil
from collections import Counter
from pathlib import Path

import yaml
from PIL import Image

from ml.detection.boxes import (clip_box_to_tile, coco_skeleton, coco_to_xyxy, load_classes, load_json, make_tiles,
                                save_json, xyxy_to_coco)

SPLITS = ("train", "valid", "dev", "test")


class SplitWriter:
    """Writes images + one _annotations.coco.json. Boxes of classes not in `classes` are dropped."""

    def __init__(self, root: Path, name: str, classes):
        self.dir = root / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.coco = coco_skeleton(classes)
        self.allowed = {c["id"] for c in classes}

    def add(self, image: Image.Image, file_name: str, boxes_with_cat: list, source: str):
        image.convert("RGB").save(self.dir / file_name, quality=95)
        image_id = len(self.coco["images"]) + 1
        self.coco["images"].append({"id": image_id, "file_name": file_name, "width": image.width,
                                    "height": image.height, "source": source})
        for box, cat in boxes_with_cat:
            if cat not in self.allowed:
                continue
            self.coco["annotations"].append({
                "id": len(self.coco["annotations"]) + 1, "image_id": image_id, "category_id": cat,
                "bbox": xyxy_to_coco(box), "area": (box[2] - box[0]) * (box[3] - box[1]), "iscrowd": 0})

    def close(self):
        save_json(self.coco, self.dir / "_annotations.coco.json")
        return self.coco


def tile_photo(writer: SplitWriter, img: Image.Image, stem: str, anns, tile: int, keep_empty: float, rng):
    """Add overlapping tiles of one photo, plus one shrunk copy of the whole photo."""
    for t in make_tiles(img.width, img.height, tile=tile):
        boxes = [(b, c) for b, c in ((clip_box_to_tile(box, t), cat) for box, cat in anns) if b]
        if not boxes and rng.random() > keep_empty:
            continue                                     # keep only some empty tiles (background examples)
        writer.add(img.crop(tuple(t.box)), f"co-{stem}-x{t.x}-y{t.y}.jpg", boxes, "company")
    scale = tile / max(img.size)
    if scale < 1:
        small = img.resize((round(img.width * scale), round(img.height * scale)))
        writer.add(small, f"co-{stem}-whole.jpg", [([v * scale for v in b], c) for b, c in anns], "company")


def _norm(name: str) -> str:
    """'Circuit-Breaker' and 'circuit breaker' are the same class name."""
    return " ".join(name.lower().replace("-", " ").replace("_", " ").split())


def add_public(writers: dict, public_dir: Path, class_map: dict, our_ids: dict, info: dict, tile: int):
    """class_map: {"<dataset folder>": {"<their class name>": "<our class name or null>"}}"""
    for ds_name, mapping in class_map.items():
        norm_map = {_norm(k): v for k, v in (mapping or {}).items()}
        for split in ("train", "valid"):                 # never test
            ann_file = public_dir / ds_name / split / "_annotations.coco.json"
            if not ann_file.exists():
                info["warnings"].append(f"public {ds_name}/{split}: not found at {ann_file}, skipped")
                continue
            data = load_json(ann_file)
            cat_map = {c["id"]: our_ids.get(norm_map.get(_norm(c["name"])) or "") for c in data["categories"]}
            unmapped = sorted({c["name"] for c in data["categories"] if _norm(c["name"]) not in norm_map})
            if unmapped:
                info["warnings"].append(f"public {ds_name}/{split}: classes not in the map, ignored: {unmapped}")
            by_img = {}
            for a in data["annotations"]:
                if cat_map.get(a["category_id"]):
                    by_img.setdefault(a["image_id"], []).append((coco_to_xyxy(a["bbox"]), cat_map[a["category_id"]]))
            for im in data["images"]:
                if im["id"] not in by_img:
                    continue                             # only images that contain a class we use
                with Image.open(ann_file.parent / im["file_name"]) as pil:
                    pil = pil.convert("RGB")
                    scale = min(1.0, tile / max(pil.size))  # big public photos: shrink to the tile size
                    if scale < 1:
                        pil = pil.resize((round(pil.width * scale), round(pil.height * scale)))
                    writers[split].add(pil, f"pub-{ds_name}-{Path(im['file_name']).stem}.jpg",
                                       [([v * scale for v in b], c) for b, c in by_img[im["id"]]],
                                       f"public:{ds_name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", type=Path, help="company photo labels (COCO), the test answer key. "
                    "Leave out to build only the public training data (train/valid), e.g. to train while labelling")
    ap.add_argument("--photos", type=Path, default=Path("data/private/company-dataset"))
    ap.add_argument("--splits", type=Path, default=Path("ml/detection/splits.yaml"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--public-dir", type=Path, default=Path("data/external"))
    ap.add_argument("--public-map", type=Path)
    ap.add_argument("--tile", type=int, default=1024)
    ap.add_argument("--keep-empty", type=float, default=0.3, help="share of company tiles with no parts to keep")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    splits = yaml.safe_load(a.splits.read_text(encoding="utf-8")) or {}
    listed = [n for s in SPLITS for n in (splits.get(s) or [])]
    dupes = sorted({n for n in listed if listed.count(n) > 1})
    if dupes:
        raise SystemExit(f"A photo is listed in two splits: {dupes}")
    where = {n: s for s in SPLITS for n in (splits.get(s) or [])}

    if a.out.exists():
        shutil.rmtree(a.out)
    rng = random.Random(a.seed)
    classes = load_classes()
    trained = [c for c in classes if c.get("detector")]
    if not trained:
        raise SystemExit("No class has `detector: true` in classes.yaml: nothing to train.")
    our_ids = {c["name"]: c["id"] for c in trained}

    writers = {"train": SplitWriter(a.out, "train", trained), "valid": SplitWriter(a.out, "valid", trained),
               "test": SplitWriter(a.out, "test", classes)}
    full = {"test": SplitWriter(a.out, "test_full", classes), "dev": SplitWriter(a.out, "dev_full", classes)}
    info = {"seed": a.seed, "tile": a.tile, "trained_classes": [c["name"] for c in trained],
            "zero_shot_classes": [c["name"] for c in classes if not c.get("detector")],
            "photos": {}, "warnings": []}

    labels = load_json(a.labels) if a.labels else {"images": [], "annotations": []}
    for im in labels["images"]:
        split = where.get(Path(im["file_name"]).stem) or where.get(im["file_name"])
        if not split:
            info["warnings"].append(f"{im['file_name']}: not in splits.yaml, not used")
            continue
        anns = [(coco_to_xyxy(x["bbox"]), x["category_id"]) for x in labels["annotations"] if x["image_id"] == im["id"]]
        img = Image.open(a.photos / im["file_name"]).convert("RGB")
        if split in ("train", "valid", "test"):
            tile_photo(writers[split], img, Path(im["file_name"]).stem, anns, a.tile, a.keep_empty, rng)
        if split in full:
            full[split].add(img, im["file_name"], anns, "company")
        info["photos"][im["file_name"]] = {"split": split, "boxes": len(anns)}

    if a.public_map:
        add_public(writers, a.public_dir, yaml.safe_load(a.public_map.read_text(encoding="utf-8")) or {},
                   our_ids, info, a.tile)

    names = {c["id"]: c["name"] for c in classes}
    report = {**writers, "test_full": full["test"], "dev_full": full["dev"]}
    for s, w in report.items():
        coco = w.close()
        info[s] = {"images": len(coco["images"]),
                   "boxes_per_class": dict(Counter(names[x["category_id"]] for x in coco["annotations"])),
                   "sources": dict(Counter(i["source"] for i in coco["images"]))}
    info["labels_sha256"] = hashlib.sha256(a.labels.read_bytes()).hexdigest() if a.labels else None
    save_json(info, a.out / "dataset_info.json")
    for s in report:
        print(f"{s:<9} {info[s]}")
    for wmsg in info["warnings"]:
        print("WARNING:", wmsg)
    for s in ("train", "valid"):
        if info[s]["images"] == 0:
            raise SystemExit(f"The {s} split is empty. Download the public datasets into {a.public_dir} "
                             f"(README step 4) and pass --public-map.")


if __name__ == "__main__":
    main()
