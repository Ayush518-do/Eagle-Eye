"""Match an OCR reading to the tag list from the drawing, keeping the raw text visible.

OCR often swaps look-alike characters: "C811" for "CB11", "PSl1" for "PS11".
We try those swaps and allow at most one remaining character difference. If two expected tags
are equally close, we refuse to choose (returns None) so a person reviews it.
"""
from dataclasses import dataclass
from typing import Iterable, Optional

# OCR character -> what it often should be
LOOKALIKES = {"8": "B", "0": "O", "O": "0", "I": "1", "L": "1", "l": "1", "|": "1", "5": "S", "S": "5", "B": "8"}


@dataclass
class Match:
    raw: str
    tag: Optional[str]
    distance: int
    exact: bool


def _norm(s: str) -> str:
    return "".join(ch for ch in s.upper() if ch.isalnum())


def _distance(a: str, b: str) -> int:
    """Edit distance where a look-alike swap costs 0 and other differences cost 1."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            same = ca == cb or LOOKALIKES.get(ca) == cb
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (0 if same else 1)))
        prev = cur
    return prev[-1]


def match_tag(raw: str, expected: Iterable[str], max_distance: int = 1) -> Match:
    text = _norm(raw)
    tags = [_norm(t) for t in expected]
    if text in tags:
        return Match(raw, text, 0, True)
    scored = sorted((_distance(text, t), t) for t in tags)
    if not scored or scored[0][0] > max_distance:
        return Match(raw, None, scored[0][0] if scored else -1, False)
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return Match(raw, None, scored[0][0], False)  # ambiguous: let a person decide
    return Match(raw, scored[0][1], scored[0][0], False)
