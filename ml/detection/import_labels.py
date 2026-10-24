"""Step 3: turn the Label Studio export into one COCO file for our full-size photos.

    python -m ml.detection.import_labels data/private/labels/ls_export.json \
        --photos data/private/company-dataset --out data/private/labels/company_coco.json

In Label Studio: Export -> "JSON" (not "JSON-MIN", not "COCO"). Only boxes a person submitted are
used (the "annotations"); OWLv2's suggestions ("predictions") are ignored unless someone accepted them.
"""
import argparse
from pathlib import Path
from urllib.parse import unquote

from PIL import Image

from ml.detection.boxes import coco_skeleton, from_label_studio_result, load_classes, load_json, save_json, xyxy_to_coco


def photo_name_from_url(url: str) -> str:
    # "/data/local-files/?d=company-dataset/cab1_full_front.jpg" -> "cab1_full_front.jpg"
    return Path(unquote(url).split("?d=")[-1]).name


def convert(ls_tasks: list, photos_dir: Path) -> tuple[dict, list[str]]:
    classes = load_classes()
    ids = {c["name"]: c["id"] for c in classes}
    coco = coco_skeleton(classes)
    problems = []
    for task in ls_tasks:
        name = photo_name_from_url(task["data"]["image"])
        anns = [a for a in task.get("annotations", []) if not a.get("was_cancelled")]
        if not anns:
            problems.append(f"{name}: no submitted annotation, skipped")
            continue
        path = photos_dir / name
        with Image.open(path) as im:
            w, h = im.size
        image_id = len(coco["images"]) + 1
        coco["images"].append({"id": image_id, "file_name": name, "width": w, "height": h})
        for r in anns[-1]["result"]:            # newest submitted annotation
            if r.get("type") != "rectanglelabels":
                continue
            label, box = from_label_studio_result(r)
            if label not in ids:
                problems.append(f"{name}: unknown label {label!r}, skipped")
                continue
            box = [max(0, box[0]), max(0, box[1]), min(w, box[2]), min(h, box[3])]
            coco["annotations"].append({
                "id": len(coco["annotations"]) + 1, "image_id": image_id, "category_id": ids[label],
                "bbox": xyxy_to_coco(box), "area": (box[2] - box[0]) * (box[3] - box[1]), "iscrowd": 0,
            })
    return coco, problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("export", type=Path)
    ap.add_argument("--photos", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    coco, problems = convert(load_json(a.export), a.photos)
    save_json(coco, a.out)
    names = {c["id"]: c["name"] for c in coco["categories"]}
    for img in coco["images"]:
        per = {}
        for an in coco["annotations"]:
            if an["image_id"] == img["id"]:
                per[names[an["category_id"]]] = per.get(names[an["category_id"]], 0) + 1
        print(f'{img["file_name"]}: {per}')
    for p in problems:
        print("WARNING:", p)
    print(f"Wrote {a.out}")


if __name__ == "__main__":
    main()
