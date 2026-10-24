"""Compare a new photo with an approved reference photo of the same cabinet (OpenCV).

    python -m ml.compare_reference REFERENCE.jpg NEW.jpg --out result.jpg

1. Align: SIFT feature points + RANSAC homography warp the new photo onto the reference.
2. Difference: per-pixel colour difference after blur, threshold, clean-up.
3. Report: red boxes around regions that changed (parts missing, added or moved).
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def load(p, width=1500):
    im = cv2.imread(str(p))
    s = width / im.shape[1]
    return cv2.resize(im, (width, int(im.shape[0] * s)))


def compare(ref_path, new_path, out_path, min_area_frac=0.0015):
    ref, new = load(ref_path), load(new_path)
    g1, g2 = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY), cv2.cvtColor(new, cv2.COLOR_BGR2GRAY)
    sift = cv2.SIFT_create(6000)
    k1, d1 = sift.detectAndCompute(g1, None)
    k2, d2 = sift.detectAndCompute(g2, None)
    matches = cv2.FlannBasedMatcher().knnMatch(d2, d1, k=2)
    good = [m for m, n in matches if m.distance < 0.7 * n.distance]
    src = np.float32([k2[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([k1[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    aligned = cv2.warpPerspective(new, H, (ref.shape[1], ref.shape[0]))
    valid = cv2.warpPerspective(np.full(g2.shape, 255, np.uint8), H, (ref.shape[1], ref.shape[0]))

    a = cv2.GaussianBlur(ref, (7, 7), 0).astype(np.int16)
    b = cv2.GaussianBlur(aligned, (7, 7), 0).astype(np.int16)
    diff = np.abs(a - b).max(axis=2).astype(np.uint8)
    diff[cv2.erode(valid, np.ones((25, 25), np.uint8)) == 0] = 0
    _, mask = cv2.threshold(diff, 45, 255, cv2.THRESH_BINARY)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    min_area = min_area_frac * mask.size
    regions = [tuple(stats[i][:4]) for i in range(1, n) if stats[i][4] >= min_area]

    vis = aligned.copy()
    for i, (x, y, w, h) in enumerate(sorted(regions, key=lambda r: (r[1], r[0])), 1):
        cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 0, 255), 5)
        cv2.putText(vis, f"CHANGE {i}", (x, max(30, y - 10)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
    side = np.hstack([ref, vis])
    cv2.putText(side, "REFERENCE (approved)", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 160, 0), 4)
    cv2.putText(side, "NEW PHOTO - differences", (ref.shape[1] + 20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 255), 4)
    cv2.imwrite(str(out_path), side)
    compare.last_H = H
    return len(good), int(inl.sum()), sorted(regions, key=lambda r: (r[1], r[0])), ref.shape, mask, vis, side


def name_changes(map_path, mask, side, ref_w):
    """Which known parts of the reference photo lie under the changed pixels."""
    m = json.loads(Path(map_path).read_text(encoding="utf-8"))
    H, W = mask.shape
    hits = []
    for name, (x0, y0, x1, y1) in m["parts"].items():
        X0, Y0, X1, Y1 = int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)
        frac = float((mask[Y0:Y1, X0:X1] > 0).mean()) if X1 > X0 and Y1 > Y0 else 0.0
        if frac >= 0.35:
            hits.append((name, frac))
            cv2.rectangle(side, (ref_w + X0, Y0), (ref_w + X1, Y1), (0, 140, 255), 3)
            cv2.putText(side, name.split(" (")[0], (ref_w + X0, Y1 + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 140, 255), 2)
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reference", type=Path)
    ap.add_argument("new", type=Path)
    ap.add_argument("--map", type=Path, help="part map of the reference photo (default: data/private/reference_maps/<reference>.json)")
    ap.add_argument("--out", type=Path, default=Path("data/private/compare_result.jpg"))
    a = ap.parse_args()
    good, inliers, regions, shape, mask, vis, side = compare(a.reference, a.new, a.out)
    map_path = a.map or Path("data/private/reference_maps") / (a.reference.stem + ".json")
    hits = name_changes(map_path, mask, side, shape[1]) if Path(map_path).exists() else None
    if hits is not None:
        cv2.imwrite(str(a.out), side)
    H, W = shape[:2]
    print(f"Aligned new photo to reference using {inliers} matching points (of {good}).")
    if not regions:
        print("No significant differences: matches the reference.")
    for i, (x, y, w, h) in enumerate(regions, 1):
        cx, cy = (x + w / 2) / W, (y + h / 2) / H
        v = "top" if cy < .33 else "middle" if cy < .66 else "bottom"
        hz = "left" if cx < .33 else "centre" if cx < .66 else "right"
        print(f"  CHANGE {i}: {v}-{hz} area, {w}x{h} px  -> part missing/added/moved: needs inspection")
    if hits is not None:
        missing = [h for h in hits if h[1] >= 0.6]
        partly = [h for h in hits if h[1] < 0.6]
        print("\nMISSING or replaced (most of the part changed):")
        for name, frac in missing:
            print(f"  - {name:<45} ({frac:.0%} of its area changed)")
        if not missing:
            print("  none")
        if partly:
            print("Partly changed (edge of a change, please check):")
            for name, frac in partly:
                print(f"  - {name:<45} ({frac:.0%} of its area changed)")
        if not hits:
            print("  none of the mapped parts")
    print(f"Visual result saved: {a.out}")


if __name__ == "__main__":
    main()
