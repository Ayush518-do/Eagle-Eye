"""Split images into train / test by GROUP (one cabinet = one group), never by single photo.

Near-identical photos of the same cabinet on both sides would make test scores look better
than they are. Input is a CSV with columns: image,group

Usage:
    python -m ml.detection.split data/private/groups.csv --test-groups CAB-B --out data/private/split.json
"""
import argparse
import csv
import json
from pathlib import Path


def split(rows: list[dict], test_groups: set[str]) -> dict:
    groups = {r["group"] for r in rows}
    unknown = test_groups - groups
    if unknown:
        raise ValueError(f"Test groups not in the CSV: {sorted(unknown)}")
    if not test_groups or test_groups == groups:
        raise ValueError("Need at least one group for training and one for testing.")
    return {
        "train": sorted(r["image"] for r in rows if r["group"] not in test_groups),
        "test": sorted(r["image"] for r in rows if r["group"] in test_groups),
        "test_groups": sorted(test_groups),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=Path)
    ap.add_argument("--test-groups", nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    with a.csv.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    result = split(rows, set(a.test_groups))
    a.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"train={len(result['train'])} test={len(result['test'])} -> {a.out}")


if __name__ == "__main__":
    main()
