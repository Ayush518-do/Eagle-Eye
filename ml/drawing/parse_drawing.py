"""Read the cabinet drawing PDF and list the parts it expects (contract A in docs/contracts.md).

Starter version. It finds tag names (CB11, PS11, DS1, …) with their page and position, and has a
helper for text printed as a vertical stack of single characters (how PS11–PS23 ratings appear
in the company drawing). The BOM-table reader must be fitted to the real drawing layout.

Usage:
    python -m ml.drawing.parse_drawing data/private/drawing.pdf > data/private/expected.json
"""
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

PARSER_VERSION = "drawing-parser 0.1.0"
# Tag prefixes seen so far. Extend after reading the drawing's legend.
TAG_PATTERN = re.compile(r"^(CB|PS|DS|K|KA|F|Q|X|A)\d{1,3}$")


@dataclass
class Word:
    text: str
    page: int
    x0: float
    top: float
    x1: float
    bottom: float


def extract_words(pdf_path: Path) -> list[Word]:
    words: list[Word] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            for w in page.extract_words(keep_blank_chars=False, use_text_flow=False):
                words.append(Word(w["text"], page_no, w["x0"], w["top"], w["x1"], w["bottom"]))
    return words


def find_tags(words: list[Word]) -> dict[str, list[Word]]:
    """Every tag-like word, grouped by tag. A tag may appear on several pages."""
    found: dict[str, list[Word]] = {}
    for w in words:
        t = w.text.strip().upper()
        if TAG_PATTERN.match(t):
            found.setdefault(t, []).append(w)
    return found


def rebuild_stacked_text(chars: list[Word], x_tolerance: float = 2.0) -> list[str]:
    """Join single characters that sit in the same column, top to bottom.

    Example: characters "2", "4", "V" placed one under another at x≈100 -> "24V".
    Returns one string per column, left to right. Callers must still treat the result as
    uncertain (needs_review) until it has been checked on the real drawing.
    """
    columns: list[list[Word]] = []
    for c in sorted(chars, key=lambda c: c.x0):
        if columns and abs(columns[-1][0].x0 - c.x0) <= x_tolerance and columns[-1][0].page == c.page:
            columns[-1].append(c)
        else:
            columns.append([c])
    return ["".join(ch.text for ch in sorted(col, key=lambda c: c.top)) for col in columns]


def to_contract(pdf_path: Path) -> dict:
    words = extract_words(pdf_path)
    tags = find_tags(words)
    items = []
    for tag in sorted(tags):
        first = min(tags[tag], key=lambda w: w.page)
        items.append({
            "tag": tag,
            "part_number": None,
            "description": None,
            "quantity": 1,
            # Ratings are not read yet: say so instead of guessing.
            "rating": {"value": None, "source": "schematic", "page": None, "needs_review": True},
            "source_page": first.page,
        })
    return {
        "contract_version": "0.2",
        "drawing_file_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        "parser_version": PARSER_VERSION,
        "items": items,
    }


if __name__ == "__main__":
    print(json.dumps(to_contract(Path(sys.argv[1])), indent=2))
