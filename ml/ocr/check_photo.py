"""Compare cabinet photos with the drawing: tags found, ratings, and order. No training involved.

    python -m ml.ocr.check_photo data/private/company-dataset/cab1_power_supplies_closeup.jpg \
        --expected data/private/expected_items.json --out data/private/checks/ps_closeup.json

For every arrangement group (row/column of parts in the drawing) with at least 2 tags read in the photo:
  * each expected tag: FOUND (sticker read) or NOT READ (inconclusive: not proof it's missing)
  * rating: MATCH, MISMATCH (potential mismatch: a person checks), or NOT READ
  * order: the tags read, sorted by position in the photo, compared with the drawing's order
Tags read that the drawing doesn't list are reported as UNEXPECTED (needs review: could be an OCR error).

--override TAG=VALUE changes an expected rating before comparing. It exists only to demonstrate that
a wrong rating is caught; every report made with it is marked "synthetic": true.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageOps

from ml.ocr.ratings import assign_ratings, rating_observations
from ml.ocr.read_tags import find_tags, read_raw


def lcs(a: list, b: list) -> list:
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) - 1, -1, -1):
        for j in range(len(b) - 1, -1, -1):
            dp[i][j] = dp[i + 1][j + 1] + 1 if a[i] == b[j] else max(dp[i + 1][j], dp[i][j + 1])
    out, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            out.append(a[i]); i += 1; j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return out


def _norm_rating(v: str | None):
    return None if not v else v.replace(" ", "").upper()


def check(photo: Path, expected: dict, overrides: dict | None = None) -> dict:
    items = {it["tag"]: it for it in expected["items"]}
    for tag, value in (overrides or {}).items():
        items[tag] = {**items[tag], "rating": {**items[tag]["rating"], "value": value}}
    image = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
    raw = read_raw(image)
    stickers = find_tags(image, list(items), raw=raw)
    ratings = assign_ratings(stickers, rating_observations(raw))

    pos = {}
    for s in stickers:                       # a tag may have 2 stickers: use the average position
        pos.setdefault(s["tag"], []).append(((s["bbox"][0] + s["bbox"][2]) / 2, (s["bbox"][1] + s["bbox"][3]) / 2))
    centre = {t: (sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps)) for t, ps in pos.items()}

    groups = []
    for g in expected.get("arrangement_groups", []):
        seen = [t for t in g["tags"] if t in centre]
        if len(seen) < 2:
            continue
        axis = 1 if g["direction"] == "top_to_bottom" else 0
        observed = sorted(seen, key=lambda t: centre[t][axis])
        expected_order = [t for t in g["tags"] if t in seen]
        keep = lcs(expected_order, observed)
        rows = []
        for t in g["tags"]:
            exp = items[t]["rating"]
            got = ratings.get(t)
            if t not in centre:
                status, rating_status = "not_read", None
            else:
                status = "found"
                if not exp.get("value"):
                    rating_status = "no_expected_rating"
                elif not got:
                    rating_status = "not_read"
                elif _norm_rating(got["value"]) == _norm_rating(exp["value"]):
                    rating_status = "match"
                else:
                    rating_status = "mismatch"
            rows.append({"tag": t, "status": status, "expected_rating": exp.get("value"),
                         "expected_rating_inferred": exp.get("source") == "bom_count",
                         "read_rating": got["value"] if got else None,
                         "read_rating_raw": got["raw"] if got else None, "rating": rating_status})
        groups.append({"group": g["group"], "direction": g["direction"], "expected_order": expected_order,
                       "observed_order": observed, "out_of_order": [t for t in observed if t not in keep],
                       "order": "matches" if observed == expected_order else "order_changed", "tags": rows})

    unexpected = sorted({s["tag"] for s in stickers} - set(items))
    return {"photo": photo.name, "synthetic": bool(overrides), "overrides": overrides or {},
            "tags_read": sorted(centre), "groups": groups, "unexpected": unexpected}


def print_report(r: dict) -> None:
    print(f"\n=== {r['photo']}" + ("   [SYNTHETIC: expected ratings changed " + str(r["overrides"]) + "]" if r["synthetic"] else ""))
    if not r["groups"]:
        print("  no group with 2+ readable tags in this photo")
    for g in r["groups"]:
        print(f"  {g['group']}: order {g['order'].upper()}" + (f" (out of order: {g['out_of_order']})" if g["out_of_order"] else ""))
        for row in g["tags"]:
            exp = (row["expected_rating"] or "-") + ("*" if row["expected_rating_inferred"] else "")
            print(f"    {row['tag']:<6} {row['status']:<9} expected {exp:<6} read {row['read_rating'] or '-':<6} -> {row['rating'] or 'inconclusive (not read)'}")
    if r["unexpected"]:
        print(f"  UNEXPECTED tags (not in drawing): {r['unexpected']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("photos", nargs="+", type=Path)
    ap.add_argument("--expected", type=Path, required=True, help="contract A from ml.drawing.parse_drawing")
    ap.add_argument("--override", action="append", default=[], metavar="TAG=VALUE",
                    help='demo only, e.g. --override "CB14=16 A"')
    ap.add_argument("--out", type=Path, help="folder for one JSON report per photo")
    a = ap.parse_args()
    expected = json.loads(a.expected.read_text(encoding="utf-8"))
    overrides = dict(o.split("=", 1) for o in a.override)
    for p in a.photos:
        r = check(p, expected, overrides)
        print_report(r)
        if a.out:
            a.out.mkdir(parents=True, exist_ok=True)
            (a.out / f"{p.stem}{'_synthetic' if overrides else ''}.json").write_text(json.dumps(r, indent=2), encoding="utf-8")
    print("\n* expected rating inferred from the BOM count (needs review)")


if __name__ == "__main__":
    main()
