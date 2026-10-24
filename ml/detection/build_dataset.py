"""Step 4: build the training dataset (tiles + public data) in the layout RF-DETR expects.

    python -m ml.detection.build_dataset --labels data/private/labels/company_coco.json \
        --photos data/private/company-dataset --splits ml/detection/splits.yaml \
        --public-map ml/detection/public_class_map.yaml --out data/private/rfdetr_dataset

Output:
    rfdetr_dataset/
      train/_annotations.coco.json + tile images
      valid/_annotations.coco.json + tile images
      test/_annotations.coco.json  + tile images
      test_full/_annotations.coco.json + the full-size test photos   (for evaluate.py)
      dataset_info.json   which photo went where, how many boxes per class, source of every image

Rules that keep the evaluation honest:
  * a photo goes to exactly one split, decided in splits.yaml (by cabinet, never by tile);
  * public images go only to train/valid, never to test;
  * every image name carries its source ("co-" company, "pub-<name>-" public).
"""
import argparse
import hashlib
import random
import shutil
from collections import Counter
from pathlib import Path

import yaml
from PIL import Image

from ml.detection.boxes import (Tile, clip_box_to_tile, coco_skeleton, coco_to_xyxy, load_classes, load_json,
                                make_tiles, save_json, xyxy_to_coco)


class SplitWriter:
    def __init__(self, root: Path, name: str, classes):
        self.dir = root / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.coco = coco_skeleton(classes)
        self.name = name

    def add(self, image: Image.Image, file_name: str, boxes_with_cat: list, source: str):
        image.convert("RGB").save(self.dir / file_name, quality=95)
        image_id = len(self.coco["images"]) + 1
        self.coco["images"].append({"id": image_id, "file_name": file_name, "width": image.width,
                                    "height": image.height, "source": source})
        for box, cat in boxes_with_cat:
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
    if scale < 1:                                        # the whole photo, shrunk: teaches large parts too
        small = img.resize((round(img.width * scale), round(img.height * scale)))
        boxes = [([v * scale for v in box], cat) for box, cat in anns]
        writer.add(small, f"co-{stem}-whole.jpg", boxes, "company")


def _norm(name: str) -> str:
    """'Circuit-Breaker' and 'circuit breaker' are the same class name."""
    return " ".join(name.lower().replace("-", " ").replace("_", " ").split())


def add_public(writers: dict, public_dir: Path, class_map: dict, our_ids: dict, info: dict):
    """class_map: {"<dataset folder>": {"<their class name>": "<our class name or null>"}}"""
    for ds_name, mapping in class_map.items():
        for split in ("train", "valid"):                 # never test
            ann_file = public_dir / ds_name / split / "_annotations.coco.json"
            if not ann_file.exists():
                info["warnings"].append(f"public {ds_name}/{split}: not found, skipped")
                continue
            data = load_json(ann_file)
            norm_map = {_norm(k): v for k, v in mapping.items()}
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
                    writers[split].add(pil.copy(), f"pub-{ds_name}-{Path(im['file_name']).stem}.jpg",
                                       by_img[im["id"]], f"public:{ds_name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--photos", type=Path, required=True)
    ap.add_argument("--splits", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--public-dir", type=Path, default=Path("data/external"))
    ap.add_argument("--public-map", type=Path)
    ap.add_argument("--tile", type=int, default=1024)
    ap.add_argument("--keep-empty", type=float, default=0.3, help="share of tiles with no parts to keep")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    if a.out.exists():
        shutil.rmtree(a.out)
    rng = random.Random(a.seed)
    classes = load_classes()
    our_ids = {c["name"]: c["id"] for c in classes}
    splits = yaml.safe_load(a.splits.read_text(encoding="utf-8"))
    listed = [name for s in ("train", "valid", "test") for name in (splits.get(s) or [])]
    dupes = sorted({n for n in listed if listed.count(n) > 1})
    where = {name: s for s in ("train", "valid", "test") for name in (splits.get(s) or [])}
    if dupes:
        raise SystemExit(f"A photo is listed in two splits: {dupes}")

    labels = load_json(a.labels)
    writers = {s: SplitWriter(a.out, s, classes) for s in ("train", "valid", "test")}
    test_full = SplitWriter(a.out, "test_full", classes)
    info = {"seed": a.seed, "tile": a.tile, "photos": {}, "warnings": []}

    for im in labels["images"]:
        split = where.get(Path(im["file_name"]).stem) or where.get(im["file_name"])
        if not split:
            info["warnings"].append(f"{im['file_name']}: not in splits.yaml, not used")
            continue
        anns = [(coco_to_xyxy(x["bbox"]), x["category_id"]) for x in labels["annotations"] if x["image_id"] == im["id"]]
        img = Image.open(a.photos / im["file_name"]).convert("RGB")
        tile_photo(writers[split], img, Path(im["file_name"]).stem, anns, a.tile, a.keep_empty, rng)
        if split == "test":
            test_full.add(img, im["file_name"], anns, "company")
        info["photos"][im["file_name"]] = {"split": split, "boxes": len(anns)}

    if a.public_map:
        add_public(writers, a.public_dir, yaml.safe_load(a.public_map.read_text(encoding="utf-8")) or {}, our_ids, info)

    names = {c["id"]: c["name"] for c in classes}
    for s, w in [*writers.items(), ("test_full", test_full)]:
        coco = w.close()
        info[s] = {"images": len(coco["images"]),
                   "boxes_per_class": dict(Counter(names[x["category_id"]] for x in coco["annotations"])),
                   "sources": dict(Counter(i["source"] for i in coco["images"]))}
    info["labels_sha256"] = hashlib.sha256(a.labels.read_bytes()).hexdigest()
    save_json(info, a.out / "dataset_info.json")
    for s in ("train", "valid", "test", "test_full"):
        print(f"{s:<9} {info[s]}")
    for wmsg in info["warnings"]:
        print("WARNING:", wmsg)
    for s in ("train", "valid"):
        if info[s]["images"] == 0:
            raise SystemExit(f"The {s} split is empty: RF-DETR needs both train and valid images.")


if __name__ == "__main__":
    main()
