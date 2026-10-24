"""Find rating text in a photo ("16A", "20A Power Supply", "80A Redundancy") and attach it to tags.

Only text that STARTS with an amp value counts as a rating. Input/output specifications such as
"100-240V~12A" or "24V=|40A" start with a voltage and are ignored.

Attaching a rating to a tag: the nearest rating text below the tag sticker (or directly above it in
the same column), within `max_dist` sticker sizes, and not to its left. ("100A@40°C" printed on the busbar left of the
breakers must not become a breaker's rating.) Each rating text goes to at most one tag;
the closest pairs are decided first.
"""
from __future__ import annotations

import math
import re

AMPS_FIRST = re.compile(r"^\s*(\d+(?:\.\d+)?)\s?A(?![A-Z0-9])|^\s*(\d+(?:\.\d+)?)\s?A(?=POWER|REDUNDANCY|\s)", re.I)


def parse_rating(text: str) -> str | None:
    """'16A' -> '16 A', '20A PowerSupply' -> '20 A', '16A 415V~' -> '16 A', '24V=|40A' -> None."""
    m = AMPS_FIRST.match(text.upper())
    if not m:
        return None
    v = m.group(1) or m.group(2)
    if "@" in text:                      # "100A@40°C": a busbar's thermal rating, not a device rating
        return None
    return f"{float(v):g} A"


def rating_observations(raw_readings: list[dict]) -> list[dict]:
    """From read_raw() output: rating readings, one per spot (best score kept)."""
    from ml.ocr.read_tags import _iou
    found = []
    for r in sorted(raw_readings, key=lambda r: -r["score"]):
        value = parse_rating(r["text"])
        if value and not any(f["value"] == value and _iou(f["bbox"], r["bbox"]) > 0.3 for f in found):
            found.append({"value": value, "raw": r["text"], "score": r["score"], "bbox": r["bbox"]})

    # A cut-off read inside a longer one at the same spot ("6A" inside "16A"): keep the longer one.
    def inside(a, b):      # box a mostly within box b
        ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
        return ix * iy >= 0.6 * (a[2] - a[0]) * (a[3] - a[1])
    return [f for f in found
            if not any(g is not f and g["value"] != f["value"] and g["value"].endswith(f["value"])
                       and (inside(f["bbox"], g["bbox"]) or inside(g["bbox"], f["bbox"])) for g in found)]


def _centre(b):
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def assign_ratings(tags: list[dict], ratings: list[dict], max_dist: float = 8.0) -> dict[str, dict]:
    """tags: [{'tag','bbox'}] (several stickers may share a tag). Returns {tag: rating dict + 'distance'}."""
    pairs = []
    for t in tags:
        size = max(t["bbox"][2] - t["bbox"][0], t["bbox"][3] - t["bbox"][1])
        tx, ty = _centre(t["bbox"])
        for i, r in enumerate(ratings):
            rx, ry = _centre(r["bbox"])
            if rx < t["bbox"][0] - 0.5 * size:
                continue                                     # left of the sticker
            same_column = abs(rx - tx) < size
            if ry < ty and not (same_column and ry >= t["bbox"][1] - size):
                continue                                     # above: only directly above, and close
            d = math.hypot(rx - tx, ry - ty) / size
            if d <= max_dist:
                pairs.append((d, t["tag"], i))
    result, used = {}, set()
    for d, tag, i in sorted(pairs):
        if tag in result or i in used:
            continue
        result[tag] = {**ratings[i], "distance": round(d, 2)}
        used.add(i)
    return result
