"""Visual reference-vs-candidate comparison, wrapping ml.compare_reference.compare().

Takes two local image paths (an approved reference photo and a candidate), aligns them
with SIFT + RANSAC homography, computes per-pixel colour difference and returns the
regions-of-change as bboxes in CANDIDATE-image pixel coordinates (after unwarping the
reference-space bboxes back through the inverse homography and scaling to the original
candidate resolution).

Each region carries an "area fraction" (fraction of total image area) and a derived
`change_score` in [0, 1] that saturates at ~10 % of image area. The scoring is
conservative — it tells reviewers where to look, not whether something is really missing.
"""
from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import numpy as np

from ml.compare_reference import compare, load


class ChangeRegion(TypedDict):
    bbox: list[float]       # [x1, y1, x2, y2] in CANDIDATE-image original pixel coordinates
    area_frac: float        # area / (candidate_width * candidate_height), in [0, 1]
    change_score: float     # saturating confidence that this region really changed, [0, 1]


def _unwarp_bbox(x: float, y: float, w: float, h: float, H_inv: np.ndarray) -> tuple[float, float, float, float]:
    """Map a reference-space bbox back into candidate-space via the inverse homography."""
    corners = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], dtype=np.float64)
    homog = np.hstack([corners, np.ones((4, 1))])
    projected = (H_inv @ homog.T).T
    wcol = projected[:, 2:3]
    wcol[wcol == 0] = 1e-9
    xy = projected[:, :2] / wcol
    return float(xy[:, 0].min()), float(xy[:, 1].min()), float(xy[:, 0].max()), float(xy[:, 1].max())


def compare_images(reference_path: Path, candidate_path: Path, *, min_area_frac: float = 0.0015) -> dict:
    """Run the visual compare pipeline and return a JSON-friendly summary.

    Returns a dict with:
      - regions:         list[ChangeRegion] in CANDIDATE-image original pixel coordinates
      - reference_size:  [w, h] of the ORIGINAL reference image on disk
      - candidate_size:  [w, h] of the ORIGINAL candidate image on disk
      - sift_matches:    number of inlier SIFT matches (indicative of alignment quality)
      - diagnostic:      short string: "ok" | "poor_alignment" | "no_differences"
    """
    import cv2  # heavy; imported lazily per endpoint call

    reference_path = Path(reference_path)
    candidate_path = Path(candidate_path)
    ref_full = cv2.imread(str(reference_path))
    cand_full = cv2.imread(str(candidate_path))
    if ref_full is None or cand_full is None:
        raise ValueError("Could not read one of the images.")
    ref_h, ref_w = ref_full.shape[:2]
    cand_h, cand_w = cand_full.shape[:2]

    # compare() writes a side-by-side diagnostic image to disk. We give it a throwaway
    # path in the scratchpad; the caller just wants the structured regions.
    tmp_out = reference_path.parent / f".visual_compare_{reference_path.stem}_{candidate_path.stem}.jpg"
    try:
        good, inliers, regions_resized, shape, mask, vis, side = compare(
            reference_path, candidate_path, tmp_out, min_area_frac=min_area_frac,
        )
    finally:
        try:
            tmp_out.unlink(missing_ok=True)
        except OSError:
            pass

    H = getattr(compare, "last_H", None)
    # Quality gate: 50 inlier SIFT matches is a conservative lower bound for a trustworthy
    # homography between two photos of the same cabinet shot from a similar POV. Below that,
    # the warp is noisy and change regions are not meaningful.
    if H is None or int(inliers) < 50:
        return {"regions": [], "reference_size": [ref_w, ref_h], "candidate_size": [cand_w, cand_h],
                "sift_matches": int(inliers), "diagnostic": "poor_alignment"}

    # The regions above are in the RESIZED reference frame (width 1500).  compare.load()
    # scales both inputs to width 1500 before SIFT, so H maps resized-candidate -> resized-reference.
    # To put the regions in the ORIGINAL candidate pixel coordinates:
    #   1. unwarp the resized-reference bbox back to resized-candidate via H_inv
    #   2. scale by (orig_cand_w / 1500) to recover original candidate pixels
    try:
        H_inv = np.linalg.inv(H)
    except np.linalg.LinAlgError:
        return {"regions": [], "reference_size": [ref_w, ref_h], "candidate_size": [cand_w, cand_h],
                "sift_matches": int(inliers), "diagnostic": "poor_alignment"}

    _, resized_ref_w = shape[:2][1], shape[1]
    cand_scale = cand_w / float(resized_ref_w)  # resized-ref and resized-cand share the same width (1500)
    cand_area = cand_w * cand_h

    out: list[ChangeRegion] = []
    for (x, y, w, h) in regions_resized:
        cx1, cy1, cx2, cy2 = _unwarp_bbox(float(x), float(y), float(w), float(h), H_inv)
        # scale resized-candidate coords -> original candidate coords
        bx1 = max(0.0, min(cand_w, cx1 * cand_scale))
        by1 = max(0.0, min(cand_h, cy1 * cand_scale))
        bx2 = max(0.0, min(cand_w, cx2 * cand_scale))
        by2 = max(0.0, min(cand_h, cy2 * cand_scale))
        if bx2 - bx1 < 2 or by2 - by1 < 2:
            continue
        area_frac = max(0.0, min(1.0, ((bx2 - bx1) * (by2 - by1)) / cand_area))
        if area_frac > 0.5:
            # A region covering more than half the image is almost always a warping artefact,
            # not a real change — drop it rather than reporting a bogus "everything changed".
            continue
        change_score = min(1.0, area_frac / 0.10)  # saturate at 10 % of image area
        out.append({
            "bbox": [round(bx1, 1), round(by1, 1), round(bx2, 1), round(by2, 1)],
            "area_frac": round(area_frac, 4),
            "change_score": round(change_score, 3),
        })

    diagnostic = "ok" if out else "no_differences"
    return {
        "regions": out,
        "reference_size": [int(ref_w), int(ref_h)],
        "candidate_size": [int(cand_w), int(cand_h)],
        "sift_matches": int(inliers),
        "diagnostic": diagnostic,
    }
