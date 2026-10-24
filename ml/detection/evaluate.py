"""Step 7: score each model, and both combined, on the company TEST photos (never trained on).

    python -m ml.detection.evaluate --truth data/private/rfdetr_dataset/test_full \
        --pred-dir runs/eval/test --out runs/eval/test_metrics.json

Reads the boxes saved by predict_all.py (one subfolder per source: detector/, zero_shot/).
For each source, and for "combined" (all sources merged), per class:
  precision = of the boxes drawn, how many were right
  recall    = of the real parts, how many were found
  AP50      = both combined over every confidence level, with a box counted right when it overlaps
              the true box by IoU >= 0.5 (IoU = overlap area / combined area)
Each model scores on a different scale (OWLv2's scores are much lower), so each gets its own
threshold for precision/recall. A class with no real parts in the test photos gets "no test data".
"""
import argparse
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ml.detection.boxes import coco_to_xyxy, iou, load_json, merge_tile_detections, save_json

DEFAULT_THRESHOLDS = {"detector": 0.3, "zero_shot": 0.15}


def match(preds: list[dict], truths: list[list[float]], iou_threshold: float = 0.5):
    """Greedy matching, best score first. Returns [(score, is_true_positive)]."""
    used, out = set(), []
    for p in sorted(preds, key=lambda d: -d["score"]):
        best, best_iou = None, iou_threshold
        for i, t in enumerate(truths):
            v = iou(p["bbox"], t)
            if i not in used and v >= best_iou:
                best, best_iou = i, v
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
            preds = [p for p in predictions_by_image.get(Path(im["file_name"]).stem, []) if p["class_name"] == name]
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


def load_predictions(pred_dir: Path) -> dict:
    """{source: {photo_stem: [{'bbox','score','class_name'}]}} from predict_all.py output."""
    out = {}
    for src_dir in sorted(p for p in pred_dir.iterdir() if p.is_dir() and p.name != "previews"):
        out[src_dir.name] = {}
        for f in src_dir.glob("*.json"):
            obs = load_json(f)["observations"]
            out[src_dir.name][f.stem] = [{"bbox": o["bbox"], "score": o["confidence"], "class_name": o["class_name"]}
                                         for o in obs if o["kind"] == "component"]
    return out


def combine(preds: dict, thresholds: dict) -> dict:
    """Merge all sources: keep each source's boxes above its own threshold, then remove duplicates
    (the same part found by two models) per class."""
    photos = {stem for per in preds.values() for stem in per}
    return {stem: merge_tile_detections([d for src, per in preds.items() for d in per.get(stem, [])
                                         if d["score"] >= thresholds.get(src, 0.3)])
            for stem in photos}


def evaluate(truth_dir: Path, pred_dir: Path, thresholds: dict) -> dict:
    coco = load_json(truth_dir / "_annotations.coco.json")
    preds = load_predictions(pred_dir)
    per_source = {src: score(p, coco, thresholds.get(src, 0.3)) for src, p in preds.items()}
    if len(preds) > 1:
        per_source["combined"] = score(combine(preds, thresholds), coco, 0.0)
    return {
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "test_images": [im["file_name"] for im in coco["images"]],
        "thresholds": thresholds,
        "results": per_source,
        "caveat": "Company test photos, never used for training or tuning. Small test set: a first indication, "
                  "not a general accuracy figure.",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", type=Path, required=True, help="test_full folder (labels + photos)")
    ap.add_argument("--pred-dir", type=Path, required=True, help="output folder of predict_all.py")
    ap.add_argument("--threshold", action="append", default=[], metavar="SOURCE=VALUE",
                    help="e.g. --threshold detector=0.4 --threshold zero_shot=0.2")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--register-weights", type=Path, help="add this run to models/registry.json")
    a = ap.parse_args()

    thresholds = dict(DEFAULT_THRESHOLDS)
    for t in a.threshold:
        k, v = t.split("=")
        thresholds[k] = float(v)
    metrics = evaluate(a.truth, a.pred_dir, thresholds)
    save_json(metrics, a.out)

    for src, per_class in metrics["results"].items():
        print(f"\n== {src}")
        for name, m in per_class.items():
            if m["truth_boxes"] == 0:
                print(f"  {name:<13} no test data ({m['false_alarms_at_threshold']} false alarms)")
            else:
                print(f"  {name:<13} boxes {m['truth_boxes']:>3}  precision {m['precision']}  "
                      f"recall {m['recall']}  AP50 {m['AP50']}")
    print(f"\nSaved {a.out}")

    if a.register_weights:
        reg_path = Path("models/registry.json")
        reg = load_json(reg_path) if reg_path.exists() else []
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        reg.append({"weights_file": a.register_weights.name,
                    "weights_sha256": hashlib.sha256(a.register_weights.read_bytes()).hexdigest(),
                    "git_commit": commit, "metrics": metrics})
        save_json(reg, reg_path)
        print(f"Registered in {reg_path} (weights themselves stay out of Git)")


if __name__ == "__main__":
    main()
