"""Report what is actually in an image folder (and optional COCO label file) before using it.

Usage:
    python -m ml.detection.inspect_dataset data/private/photos [--coco data/private/labels.json]

Prints: image count, sizes, unreadable files, exact duplicates, and label counts per class.
It reads files only; it never changes them.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from PIL import Image

IMAGE_EXT = {".jpg", ".jpeg", ".png"}


def inspect(folder: Path, coco: Path | None = None) -> dict:
    images = sorted(p for p in folder.rglob("*") if p.suffix.lower() in IMAGE_EXT)
    sizes, corrupt, hashes = Counter(), [], {}
    duplicates = []
    for p in images:
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if digest in hashes:
            duplicates.append((str(p), hashes[digest]))
        else:
            hashes[digest] = str(p)
        try:
            with Image.open(p) as im:
                im.verify()
            with Image.open(p) as im:
                sizes[f"{im.width}x{im.height}"] += 1
        except Exception as exc:  # unreadable or truncated file
            corrupt.append(f"{p}: {exc}")

    report = {
        "image_count": len(images),
        "sizes": dict(sizes),
        "corrupt": corrupt,
        "exact_duplicates": duplicates,
        "labels": None,
    }
    if coco:
        data = json.loads(coco.read_text(encoding="utf-8"))
        names = {c["id"]: c["name"] for c in data.get("categories", [])}
        per_class = Counter(names.get(a["category_id"], f"unknown:{a['category_id']}") for a in data.get("annotations", []))
        labelled = {a["image_id"] for a in data.get("annotations", [])}
        report["labels"] = {
            "annotation_count": sum(per_class.values()),
            "per_class": dict(per_class),
            "images_in_file": len(data.get("images", [])),
            "images_without_labels": len(data.get("images", [])) - len(labelled),
        }
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", type=Path)
    ap.add_argument("--coco", type=Path)
    args = ap.parse_args()
    print(json.dumps(inspect(args.folder, args.coco), indent=2))


if __name__ == "__main__":
    main()
