"""Step 6: score the trained model on photos it never saw (the test split), honestly.

    python -m ml.detection.evaluate --weights runs/rfdetr-small-v1/checkpoint_best_total.pth \
        --test data/private/rfdetr_dataset/test_full --out runs/rfdetr-small-v1/test_metrics.json --register

Per class, on full-size photos (with the same tiled detection the app uses):
  precision = of the boxes the model drew, how many were right
  recall    = of the real parts, how many the model found
  AP50      = average precision when a box counts as right if it overlaps the true box by IoU >= 0.5
A class with no parts in the test photos gets "no test data", never a number.
"""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from ml.detection.boxes import coco_to_xyxy, iou, load_json, save_json


def match(preds: list[dict], truths: list[list[float]], iou_threshold: float = 0.5):
    """Greedy matching, best score first. Returns [(score, is_true_positive)] and the number of truths."""
    used, out = set(), []
    for p in sorted(preds, key=lambda d: -d["score"]):
        best, best_iou = None, iou_threshold
        for i, t in enumerate(truths):
            if i not in used and iou(p["bbox"], t) >= best_iou:
                best, best_iou = i, iou(p["bbox"], t)
        if best is not None:
            used.add(best)
        out.append((p["score"], best is not None))
    return out


def average_precision(scored: list[tuple[float, bool]], n_truth: int) -> float:
    """Area under the precision-recall curve (all-point interpolation, as in VOC/COCO)."""
    if n_truth == 0:
        return float("nan")
    scored = sorted(scored, key=lambda x: -x[0])
    tp = fp = 0
    recalls, precisions = [0.0], [1.0]
    for _, hit in scored:
        tp += hit
        fp += not hit
        recalls.append(tp / n_truth)
        precisions.append(tp / (tp + fp))
    for i in range(len(precisions) - 2, -1, -1):          # make precision non-increasing
        precisions[i] = max(precisions[i], precisions[i + 1])
    return sum((recalls[i] - recalls[i - 1]) * precisions[i] for i in range(1, len(recalls)))


def score(predictions_by_image: dict, coco: dict, threshold: float) -> dict:
    names = {c["id"]: c["name"] for c in coco["categories"]}
    result = {}
    for cat_id, name in names.items():
        scored, n_truth, tp_at, fp_at = [], 0, 0, 0
        for im in coco["images"]:
            truths = [coco_to_xyxy(a["bbox"]) for a in coco["annotations"]
                      if a["image_id"] == im["id"] and a["category_id"] == cat_id]
            preds = [p for p in predictions_by_image.get(im["file_name"], []) if p["class_name"] == name]
            n_truth += len(truths)
            m = match(preds, truths)
            scored += m
            tp_at += sum(hit for s, hit in m if s >= threshold)
            fp_at += sum(not hit for s, hit in m if s >= threshold)
        if n_truth == 0:
            result[name] = {"truth_boxes": 0, "note": "no test data for this class",
                            "false_alarms_at_threshold": fp_at}
            continue
        result[name] = {
            "truth_boxes": n_truth,
            "precision": round(tp_at / (tp_at + fp_at), 3) if tp_at + fp_at else None,
            "recall": round(tp_at / n_truth, 3),
            "AP50": round(average_precision(scored, n_truth), 3),
        }
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", type=Path, required=True)
    ap.add_argument("--test", type=Path, required=True, help="folder with _annotations.coco.json + full photos")
    ap.add_argument("--size", default="small")
    ap.add_argument("--threshold", type=float, default=0.3)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--register", action="store_true", help="add this run to models/registry.json")
    a = ap.parse_args()

    from ml.detection.detector import RFDETRDetector
    det = RFDETRDetector(a.weights, a.size, threshold=0.05)   # low, so AP sees the full score range
    coco = load_json(a.test / "_annotations.coco.json")
    preds = {im["file_name"]: det.predict(Image.open(a.test / im["file_name"])) for im in coco["images"]}
    metrics = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "test_images": [im["file_name"] for im in coco["images"]],
        "threshold": a.threshold,
        "per_class": score(preds, coco, a.threshold),
        "caveat": "Test = photos of cabinets not used in training. Small test set: treat as a first indication.",
    }
    save_json(metrics, a.out)
    print(json.dumps(metrics, indent=2))

    if a.register:
        reg_path = Path("models/registry.json")
        reg = load_json(reg_path) if reg_path.exists() else []
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        reg.append({"weights_file": a.weights.name, "weights_sha256": hashlib.sha256(a.weights.read_bytes()).hexdigest(),
                    "model": f"rf-detr-{a.size}", "git_commit": commit, "metrics": metrics})
        save_json(reg, reg_path)
        print(f"Registered in {reg_path} (weights themselves stay out of Git)")


if __name__ == "__main__":
    main()
