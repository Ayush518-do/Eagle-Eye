"""Terminal demo: read the drawing PDF, then check photos against it.

    python -m ml.demo data\\private\\company-dataset\\cab1_drawing_13GE03331.pdf data\\private\\company-dataset\\cab1_breakers_CB11-CB16_closeup.jpg
    (add more photos at the end; add  --override "CB14=10 A"  to show how a wrong rating is flagged)
"""
import argparse
import json
import time
from pathlib import Path

import hashlib

import ml.ocr.check_photo as check_photo
from ml.drawing.parse_drawing import to_contract
from ml.ocr.check_photo import check, print_report

_CACHE = Path(__file__).resolve().parents[1] / "data" / "private" / ".parse_cache"
_read_raw = check_photo.read_raw


UPSCALE_BELOW = 3000   # long side in pixels; smaller photos are enlarged so small labels stay readable
UPSCALE_TO = 4000


def _cached_read_raw(image, *args, **kwargs):
    """OCR each photo once; later runs reuse the saved text lines (same pixels -> same file)."""
    key = hashlib.sha256(image.tobytes()).hexdigest()
    scale = UPSCALE_TO / max(image.size) if max(image.size) < UPSCALE_BELOW else 1.0
    f = _CACHE / (f"ocr-{key}.json" if scale == 1.0 else f"ocr-{key}-up{UPSCALE_TO}.json")
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    if scale != 1.0:
        from PIL import Image
        big = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
        raw = _read_raw(big, *args, **kwargs)
        for r in raw:
            r["bbox"] = [v / scale for v in r["bbox"]]
    else:
        raw = _read_raw(image, *args, **kwargs)
    try:
        _CACHE.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(raw), encoding="utf-8")
    except (OSError, TypeError):
        pass
    return raw


check_photo.read_raw = _cached_read_raw

TYPES = {"CB": "Circuit breaker", "PS": "Power supply", "DS": "Disconnector", "D": "Diode module", "RCCB": "RCCB"}


def line(c="-", n=100):
    print(c * n)


_CURRENT_PHOTO = {}
_MAPS = Path(__file__).resolve().parents[1] / "data" / "private" / "reference_maps"


def visual_check(photo: Path):
    """Compare with the approved photo of the same view (each approved photo was verified against the drawing).
    Returns (reference name, inliers, {part: changed fraction}, picture path) or None."""
    from ml.compare_reference import compare, name_changes
    import cv2
    best = None
    for mp in sorted(_MAPS.glob("*.json")):
        m = json.loads(mp.read_text(encoding="utf-8"))
        ref = photo.parent / m["reference"]
        if not ref.exists() or ref.resolve() == photo.resolve():
            continue
        out = photo.parent.parent / f"compare_{photo.stem}.jpg"
        try:
            res = compare(ref, photo, out)
        except Exception:
            continue
        if best is None or res[1] > best[1][1]:
            best = (mp, res, ref, out)
    if best is None or best[1][1] < 100:
        return None
    mp, (_, inliers, _, shape, mask, _, side), ref, out = best
    # recompute against the winning reference so the stored homography belongs to it
    _, inliers, _, shape, mask, _, side = compare(ref, photo, out)
    H = compare.last_H
    hits = dict(name_changes(mp, mask, side, shape[1]))
    labels = read_labels_at(photo, json.loads(mp.read_text(encoding="utf-8"))["parts"], H, shape)
    cv2.imwrite(str(out), side)
    return ref.name, inliers, hits, out, labels


def read_labels_at(photo: Path, parts: dict, H, ref_shape) -> dict:
    """Read the label text exactly where each tag's label is on the approved photo (full resolution)."""
    import re
    import cv2
    import numpy as np
    from PIL import Image, ImageOps
    from ml.ocr.read_tags import _get_engine
    img = np.asarray(ImageOps.exif_transpose(Image.open(photo)).convert("RGB"))
    s = img.shape[1] / 1500.0                       # compare() works on 1500-px-wide copies
    Hi = np.linalg.inv(H)                           # reference -> new photo
    eng = _get_engine()
    rh, rw = ref_shape[:2]
    out = {}
    for tag, (x0, y0, x1, y1) in parts.items():
        if not re.fullmatch(r"[A-Z]{1,4}\d{1,3}", tag):
            continue
        pts = np.float32([[x0 * rw, y0 * rh], [x1 * rw, y0 * rh], [x1 * rw, y1 * rh], [x0 * rw, y1 * rh]]).reshape(-1, 1, 2)
        q = cv2.perspectiveTransform(pts, Hi).reshape(-1, 2) * s
        X0, Y0 = np.clip(q.min(0).astype(int), 0, None)
        X1, Y1 = q.max(0).astype(int)
        crop = img[Y0:Y1, X0:X1]
        if crop.size == 0:
            continue
        crop = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        texts = []
        for rot in (crop, cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)):
            res, _ = eng(rot)
            texts += [t.replace(" ", "").upper() for _, t, sc in (res or []) if sc > 0.6]
        tagish = [t for t in texts if re.fullmatch(r"[A-Z]{1,4}\d{1,3}", t)]
        out[tag] = tag if tag in tagish else (tagish[0] if tagish else None)
    return out


def summarize(r: dict) -> None:
    """Final verdict per drawing tag: OCR reading of the label + visual change vs the approved photo."""
    photo = _CURRENT_PHOTO["path"]
    vis = visual_check(photo)
    changed = {k: v for k, v in (vis[2] if vis else {}).items() if v >= 0.5}
    labels = vis[4] if vis else {}
    wrong_label = {t: v for t, v in labels.items() if v and v != t and t not in changed}
    present, missing, unclear, wrong, order, check = [], [], [], [], [], []
    for g in r["groups"]:
        tags = g["tags"]
        found = [t for t in tags if t["status"] == "found"]
        close_up = len(found) >= 0.6 * len(tags)
        for t in tags:
            tag = t["tag"]
            if tag in wrong_label:
                continue                       # reported below as WRONG LABEL
            if t["status"] == "found" or labels.get(tag) == tag:
                (check if tag in changed else present).append(tag)
            elif tag in changed or (close_up and vis is None):
                missing.append(tag)
            elif vis and tag in vis[2]:
                present.append(tag)          # label not readable, but part unchanged vs approved photo
            elif close_up:
                check.append(tag)
            else:
                unclear.append(tag)
            if t.get("rating") == "mismatch":
                wrong.append(f"{tag} (drawing {t['expected_rating']}, photo {t['read_rating']})")
        if g["order"] != "matches":
            order.append(f"{g['group']}: out of order {g['out_of_order']}")
    in_groups = {t["tag"] for g in r["groups"] for t in g["tags"]}
    for name in changed:
        if name not in in_groups:
            missing.append(name)
    if not r["groups"] and not vis:
        print("  RESULT: labels too small to read in this photo and no approved photo of this view - take a close-up")
        return
    if r["groups"]:
        print(f"  RESULT vs DRAWING: {len(present)} present", end="")
    else:
        print("  RESULT vs DRAWING: labels too small to read; all other parts unchanged vs approved photo", end="")
    print(f" | MISSING / replaced: {', '.join(missing)}" if missing else " | missing: none", end="")
    print(f" | WRONG RATING: {', '.join(wrong)}" if wrong else "", end="")
    print(" | WRONG LABEL: " + ", ".join(f"{t} (photo shows {v})" for t, v in wrong_label.items()) if wrong_label else "", end="")
    print(f" | ORDER: {'; '.join(order)}" if order else " | order OK")
    if check:
        print(f"  (please check by eye: {', '.join(check)})")
    if unclear:
        print(f"  (not checkable in this photo, labels too small: {', '.join(unclear)})")
    if vis:
        print(f"  [visual check vs approved photo {vis[0]} ({vis[1]} matching points); picture: {vis[3]}]")
    else:
        print("  [no approved photo of this view - drawing/OCR check only]")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("photos", nargs="*", type=Path)
    ap.add_argument("--override", action="append", default=[], metavar="TAG=VALUE")
    a = ap.parse_args()

    line("="); print(f"STEP 1  Reading the reference drawing: {a.pdf.name}"); line("=")
    t = time.time()
    A = to_contract(a.pdf)
    items = A["items"]
    print(f"Done in {time.time() - t:.1f} s\n")
    print(f"{'TAG':<7}{'TYPE':<17}{'RATING':<10}{'PART NO.':<14}{'PAGE':<6}{'LOCATION':<15}DESCRIPTION")
    line()
    for it in items:
        r = it.get("rating") or {}
        rating = (r.get("value") or "-") + (" *" if r.get("value") and r.get("needs_review") else "")
        prefix = "".join(ch for ch in it["tag"] if ch.isalpha())
        loc = (it.get("layout") or {}).get("view") or "-"
        print(f"{it['tag']:<7}{TYPES.get(prefix, it.get('component_type') or '-'):<17}{rating:<10}"
              f"{(it.get('part_number') or '-'):<14}{str(it.get('source_page') or '-'):<6}{loc:<15}{(it.get('description') or '-')[:40]}")
    line()
    print(f"{len(items)} components | {len(A.get('bom', []))} BOM lines | * = rating inferred from BOM count (needs review)\n")

    print("BOM cross-check (quantity in BOM vs tags found in drawing):")
    for c in A.get("bom_checks", []):
        print(f"  {c['part_number']:<14} BOM qty {c['bom_quantity']:<3} tags found {c['tags_found']:<3} -> {c['status'].upper()}")
    print("\nExpected arrangement (order on the layout page):")
    for g in A.get("arrangement_groups", []):
        print(f"  {g['group']:<26} {g['direction'].replace('_', ' '):<14} {' > '.join(g['tags'])}")

    if not a.photos:
        return
    overrides = dict(o.split("=", 1) for o in a.override)
    print(); line("="); print("STEP 2  Comparing photos with the drawing (OCR reads tag labels + ratings)"); line("=")
    if overrides:
        print(f"[SYNTHETIC TEST: drawing ratings changed {overrides} to show a mismatch]")
    for p in a.photos:
        t = time.time()
        _CURRENT_PHOTO["path"] = Path(p)
        r = check(p, A, overrides)
        print(f"\n=== {Path(p).name}")
        print("  [pass 1: OCR reading of each label - 'not_read' only means the label could not be read]")
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_report(r)
        print("\n".join(l for l in buf.getvalue().splitlines() if l.strip() and not l.startswith("===")))
        print("  [pass 2: final decision - label re-read at its exact spot + comparison with approved photo]")
        summarize(r)
        print(f"  ({time.time() - t:.1f} s)")
    print("\n* expected rating inferred from the BOM count (needs review)")


if __name__ == "__main__":
    main()
