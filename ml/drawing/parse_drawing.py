"""Read the cabinet drawing PDF and list the parts it expects (contract A in docs/contracts.md).

    python -m ml.drawing.parse_drawing data/private/company-dataset/cab1_drawing_13GE03331.pdf \
        --out data/private/expected_items.json

The drawing has a text layer, so nothing here is guessed from pixels. What it reads:

  * Bill of material (BOM) pages: every line -> item, manufacturer, part number, description, quantity.
  * Schematic pages: each component tag (CB11, PS12, DS1, D13, RCCB1 ...) and the rating printed just
    below it ("16A TYPE C", "40A 100-240 VAC").
  * General-arrangement page: where each tag sits (for the ghost overlay) and the order of tags in each
    row or column (for the arrangement check).
  * Cross-check: ratings found in the schematic are matched to BOM lines, and the counts compared.
    Tags with no printed rating get one only when the BOM count proves it, marked needs_review.

Reading words with a tight x_tolerance (1 point) matters: with the library default, letters of
neighbouring labels merge and ratings come out scrambled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

PARSER_VERSION = "drawing-parser 0.2.0"
CONTRACT_VERSION = "0.2"

# Tags of the components we inspect. Terminal blocks (X..), sockets etc. are left out on purpose.
COMPONENT_TAG = re.compile(r"^(CB\d{1,3}|DS\d{1,3}|PS\d{1,3}|D\d{2}|RCCB\d{1,2})$")
# Older starter pattern, kept for find_tags() callers.
TAG_PATTERN = re.compile(r"^(CB|PS|DS|K|KA|F|Q|X|A)\d{1,3}$")
RATING = re.compile(r"^(\d+(?:\.\d+)?)A$")
MIN_LABEL_HEIGHT = 4.0      # points; smaller text is the tiny tag drawn on a component outline
TINY_MAX_HEIGHT = 3.0


@dataclass
class Word:
    text: str
    page: int
    x0: float
    top: float
    x1: float
    bottom: float

    @property
    def height(self) -> float:
        return self.bottom - self.top


def extract_words(pdf_path: Path) -> list[Word]:
    words: list[Word] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            for w in page.extract_words(x_tolerance=1, y_tolerance=1, keep_blank_chars=False):
                words.append(Word(w["text"], page_no, w["x0"], w["top"], w["x1"], w["bottom"]))
    return words


def find_tags(words: list[Word]) -> dict[str, list[Word]]:
    """Every tag-like word, grouped by tag. A tag may appear on several pages."""
    found: dict[str, list[Word]] = {}
    for w in words:
        t = w.text.strip().upper()
        if TAG_PATTERN.match(t) or COMPONENT_TAG.match(t):
            found.setdefault(t, []).append(w)
    return found


def rebuild_stacked_text(chars: list[Word], x_tolerance: float = 2.0) -> list[str]:
    """Join single characters that sit in the same column, top to bottom ("2","4","V" -> "24V")."""
    columns: list[list[Word]] = []
    for c in sorted(chars, key=lambda c: c.x0):
        if columns and abs(columns[-1][0].x0 - c.x0) <= x_tolerance and columns[-1][0].page == c.page:
            columns[-1].append(c)
        else:
            columns.append([c])
    return ["".join(ch.text for ch in sorted(col, key=lambda c: c.top)) for col in columns]


# ------------------------------------------------------------------ BOM
def parse_bom(pdf_path: Path) -> list[dict]:
    """Read every 'BILL OF MATERIAL' page. Columns are found from the header words' x positions."""
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if "BILL OF MATERIAL" not in text:
                continue
            ws = page.extract_words(x_tolerance=1.5, y_tolerance=1)
            hdr = [w for w in ws if w["text"] in ("ITEM", "MANUFACTURER", "QTY")]
            if not hdr:
                continue
            header_top = min(w["top"] for w in hdr)
            xs = sorted(w["x0"] for w in hdr if abs(w["top"] - header_top) < 3)
            # ITEM, MANUFACTURER, MANUFACTURER (part no.), ITEM (short description), QTY
            if len(xs) < 5:
                continue
            col_item, col_maker, col_part, col_desc, col_qty = xs[:5]
            # group words into table rows: words within 2.5 pt of a row's first word belong to it
            body = sorted((w for w in ws if w["top"] > header_top + 5 and col_item - 5 <= w["x0"] < col_qty + 40),
                          key=lambda w: w["top"])
            lines: list[list[dict]] = []
            for w in body:
                if lines and w["top"] - lines[-1][0]["top"] <= 2.5:
                    lines[-1].append(w)
                else:
                    lines.append([w])
            for line in lines:
                cells = {"item": [], "maker": [], "part": [], "desc": [], "qty": []}
                for w in sorted(line, key=lambda w: w["x0"]):
                    x = w["x0"]
                    key = ("qty" if x >= col_qty - 3 else "desc" if x >= col_desc - 3 else
                           "part" if x >= col_part - 3 else "maker" if x >= col_maker - 3 else "item")
                    cells[key].append(w["text"])
                if not (cells["item"] and cells["item"][0].isdigit() and cells["qty"]):
                    continue
                try:
                    qty = int(cells["qty"][0])
                except ValueError:
                    continue
                rows.append({"item": int(cells["item"][0]), "manufacturer": " ".join(cells["maker"]),
                             "part_number": " ".join(cells["part"]), "description": " ".join(cells["desc"]),
                             "quantity": qty, "page": page_no})
    return sorted(rows, key=lambda r: r["item"])


# ------------------------------------------------------------------ schematic ratings
def read_ratings(words: list[Word]) -> dict[str, dict]:
    """For each component tag, the text printed just below it on a schematic page.
    Returns {tag: {"rating": "16 A" | None, "curve": "C" | None, "voltage": ... , "page": n}}."""
    by_page = defaultdict(list)
    for w in words:
        by_page[w.page].append(w)
    found: dict[str, dict] = {}
    for page, ws in sorted(by_page.items()):
        for t in ws:
            if not COMPONENT_TAG.match(t.text) or t.height < MIN_LABEL_HEIGHT:
                continue
            below = sorted((w for w in ws if 0 < w.top - t.bottom < 14 and abs(w.x0 - t.x0) < 25),
                           key=lambda w: (w.top, w.x0))
            texts = [w.text for w in below]
            amps = next((m.group(1) for m in (RATING.match(x) for x in texts) if m), None)
            curve = None
            if "TYPE" in texts and texts.index("TYPE") + 1 < len(texts):
                curve = texts[texts.index("TYPE") + 1]
            voltage = next((f"{x} VAC" for x in texts if re.fullmatch(r"\d+-\d+", x)), None)
            entry = {"rating": f"{amps} A" if amps else None, "curve": curve, "voltage": voltage, "page": page}
            # keep the first page that gives a rating; otherwise remember the first sighting
            if t.text not in found or (amps and not found[t.text]["rating"]):
                found[t.text] = entry
    return found


def component_type(tag: str, info: dict) -> str:
    if tag.startswith("PS"):
        return "power_supply"
    if re.fullmatch(r"D\d{2}", tag):
        return "redundancy_module"
    if tag.startswith("RCCB"):
        return "other"                      # residual-current breaker
    if tag.startswith("DS"):
        return "mcb" if info.get("curve") else "isolator"   # "25A TYPE C" = breaker, "40A" = isolator
    return "mcb"


# ------------------------------------------------------------------ BOM <-> tags
def _bom_candidates(bom: list[dict], ctype: str, amps: str | None) -> list[dict]:
    def has_amps(desc: str) -> bool:
        return bool(amps) and re.search(rf"(?<![\d.]){re.escape(amps)}\s?A\b", desc.upper()) is not None
    out = []
    for r in bom:
        d = r["description"].upper()
        if ctype == "power_supply" and "POWER SUPPLY" in d and "REDUNDANCY" not in d and has_amps(d):
            out.append(r)
        elif ctype == "redundancy_module" and "REDUNDANCY" in d:
            out.append(r)
        elif ctype == "mcb" and "MCB" in d and has_amps(d):
            out.append(r)
        elif ctype == "isolator" and "ISOLATOR" in d and has_amps(d):
            out.append(r)
        elif ctype == "other" and "RESIDUAL" in d and has_amps(d):
            out.append(r)
    return out


def link_bom(items: list[dict], bom: list[dict]) -> list[dict]:
    """Give items their BOM part number, infer missing ratings from BOM counts, and report count checks."""
    checks = []
    used = defaultdict(list)
    for it in items:
        amps = it["rating"]["value"].split()[0] if it["rating"]["value"] else None
        cands = _bom_candidates(bom, it["component_type"], amps)
        if len(cands) == 1:
            it["part_number"] = cands[0]["part_number"]
            it["description"] = cands[0]["description"]
            used[cands[0]["item"]].append(it["tag"])

    # Breakers with no printed rating: if exactly one breaker BOM line has room for exactly that many,
    # the rating follows from the count. Still marked needs_review: it's an inference, not a printed value.
    for ctype in ("mcb", "isolator"):
        unrated = [it for it in items if it["component_type"] == ctype and not it["rating"]["value"]]
        if not unrated:
            continue
        keyword = "MCB" if ctype == "mcb" else "ISOLATOR"
        free = [r for r in bom if keyword in r["description"].upper() and r["quantity"] - len(used[r["item"]]) == len(unrated)]
        if len(free) == 1:
            r = free[0]
            m = re.search(r"(\d+)\s?A\b", r["description"].upper())
            for it in unrated:
                it["rating"] = {"value": f"{m.group(1)} A" if m else None, "source": "bom_count", "page": r["page"],
                                "needs_review": True,
                                "note": f"No rating printed at the tag; BOM item {r['item']} has exactly "
                                        f"{len(unrated)} unassigned units"}
                it["part_number"], it["description"] = r["part_number"], r["description"]
                used[r["item"]].append(it["tag"])

    for r in bom:
        if used.get(r["item"]):
            checks.append({"bom_item": r["item"], "part_number": r["part_number"], "bom_quantity": r["quantity"],
                           "tags_found": len(used[r["item"]]), "tags": sorted(used[r["item"]]),
                           "status": "ok" if len(used[r["item"]]) == r["quantity"] else "count_differs"})
    return checks


# ------------------------------------------------------------------ layout + arrangement
def _view(x: float, page_width: float) -> str:
    third = page_width * 0.72 / 3          # the three views share the left ~72 % of the sheet
    return "left_inside" if x < third else "front_inside" if x < 2 * third else "right_inside"


def read_layout(words: list[Word], page_no: int, expected: set[str], page_width: float = 1191.0):
    """Positions and arrangement from the general-arrangement page.

    Two kinds of tag text on that page:
      * tiny text (< 3 pt) drawn ON the component: its real position  -> anchor "component"
      * callout labels (~7 pt) listed beside a view, in physical order -> anchor "callout"
    Rows come from tiny tags at the same height (left to right); columns from callout lists
    (top to bottom).
    """
    ws = [w for w in words if w.page == page_no]
    tiny = {w.text: w for w in ws if w.text in expected and w.height < TINY_MAX_HEIGHT}
    callout = {w.text: w for w in ws if w.text in expected and w.height >= MIN_LABEL_HEIGHT}

    layout = {}
    for tag in expected:
        w, anchor = (tiny[tag], "component") if tag in tiny else (callout.get(tag), "callout")
        if w:
            layout[tag] = {"page": page_no, "view": _view(w.x0, page_width),
                           "bbox": [round(w.x0, 1), round(w.top, 1), round(w.x1, 1), round(w.bottom, 1)],
                           "anchor": anchor}

    groups: list[dict] = []
    grouped: set[str] = set()
    # rows: tiny tags sharing a baseline
    rows = defaultdict(list)
    for tag, w in tiny.items():
        rows[round(w.top)].append(w)
    for _, row in sorted(rows.items()):
        row = sorted(row, key=lambda w: w.x0)
        if len(row) >= 2:
            groups.append({"tags": [w.text for w in row], "direction": "left_to_right",
                           "view": _view(row[0].x0, page_width)})
            grouped |= {w.text for w in row}
    # columns: callout labels (all labels, not only components) aligned in x, with small gaps
    labels = sorted((w for w in ws if w.height >= MIN_LABEL_HEIGHT and re.fullmatch(r"[A-Z][A-Z-]*\d+", w.text)),
                    key=lambda w: (round(w.x1 / 8), w.top))
    stacks: list[list[Word]] = []
    for w in labels:
        s = stacks[-1] if stacks else None
        if s and abs(s[-1].x1 - w.x1) < 6 and 0 < w.top - s[-1].top < 21:
            s.append(w)
        else:
            stacks.append([w])
    for s in stacks:
        tags = [w.text for w in s if w.text in expected and w.text not in grouped]
        if len(tags) >= 2:
            groups.append({"tags": tags, "direction": "top_to_bottom", "view": _view(s[0].x0, page_width)})
            grouped |= set(tags)
    for g in groups:
        g["group"] = f'{g["view"]}_{g["tags"][0]}-{g["tags"][-1]}'
    return layout, groups


def find_layout_page(words: list[Word]) -> int | None:
    pages = {w.page for w in words if w.text == "ARRANGEMENT"}
    return min(pages) if pages else None


# ------------------------------------------------------------------ contract A
_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "private" / ".parse_cache"


def to_contract(pdf_path: Path) -> dict:
    """Parse once per PDF; later calls for the same file (same SHA-256) return the saved result."""
    pdf_path = Path(pdf_path)
    sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    cached = _CACHE_DIR / f"{sha}-{PARSER_VERSION.replace(' ', '_')}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    result = _to_contract_uncached(pdf_path)
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(result), encoding="utf-8")
    except OSError:
        pass
    return result


def _to_contract_uncached(pdf_path: Path) -> dict:
    pdf_path = Path(pdf_path)
    words = extract_words(pdf_path)
    ratings = read_ratings(words)
    labelled = sorted({w.text for w in words if COMPONENT_TAG.match(w.text) and w.height >= MIN_LABEL_HEIGHT},
                      key=lambda t: (re.sub(r"\d", "", t), int(re.sub(r"\D", "", t))))
    first_page = {}
    for w in words:
        if w.text in labelled and w.height >= MIN_LABEL_HEIGHT:
            first_page.setdefault(w.text, w.page)

    items = []
    for tag in labelled:
        info = ratings.get(tag, {})
        value = info.get("rating")
        items.append({
            "tag": tag,
            "component_type": component_type(tag, info),
            "part_number": None,
            "description": None,
            "quantity": 1,
            "rating": {"value": value, "curve": info.get("curve"), "source": "schematic" if value else None,
                       "page": info.get("page"), "needs_review": value is None},
            "source_page": first_page.get(tag),
        })

    bom = parse_bom(pdf_path)
    checks = link_bom(items, bom) if bom else []

    layout_page = find_layout_page(words)
    groups = []
    if layout_page:
        with pdfplumber.open(pdf_path) as pdf:
            width = float(pdf.pages[layout_page - 1].width)
        layout, groups = read_layout(words, layout_page, set(labelled), width)
        pos = {t: (g, i) for g in groups for i, t in enumerate(g["tags"], start=1)}
        for it in items:
            if it["tag"] in layout:
                it["layout"] = layout[it["tag"]]
            if it["tag"] in pos:
                g, i = pos[it["tag"]]
                it["arrangement"] = {"group": g["group"], "position": i, "direction": g["direction"]}

    return {
        "contract_version": CONTRACT_VERSION,
        "drawing_file_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        "parser_version": PARSER_VERSION,
        "items": items,
        "bom": bom,
        "bom_checks": checks,
        "arrangement_groups": [{k: g[k] for k in ("group", "direction", "view", "tags")} for g in groups],
    }


def summary(c: dict) -> str:
    items = c["items"]
    by_type = defaultdict(int)
    for it in items:
        by_type[it["component_type"]] += 1
    lines = [f"{len(items)} components: {dict(by_type)}",
             f"ratings printed: {sum(it['rating']['source'] == 'schematic' for it in items)}, "
             f"inferred from BOM count: {sum(it['rating']['source'] == 'bom_count' for it in items)}, "
             f"unknown: {sum(it['rating']['value'] is None for it in items)}",
             f"BOM lines: {len(c['bom'])}; checks: " + ", ".join(f"{k['part_number']} {k['tags_found']}/{k['bom_quantity']} {k['status']}" for k in c["bom_checks"]),
             "arrangement groups: " + "; ".join(f"{g['group']} ({len(g['tags'])}, {g['direction']})" for g in c["arrangement_groups"])]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, help="write contract A JSON here (default: print to screen)")
    a = ap.parse_args()
    c = to_contract(a.pdf)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(c, indent=2), encoding="utf-8")
        print(summary(c))
        print(f"Wrote {a.out}")
    else:
        json.dump(c, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
