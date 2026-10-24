"""Compare what the drawing expects with what was seen in the photos.

Starter version: matches by tag text only (for example the OCR reads "CB11" and the drawing
lists CB11). Part 3 extends it with position matching, rating checks and the confidence gate.

Rules kept on purpose:
- An expected tag that was not read is "inconclusive", never "missing". One photo not showing
  a label does not prove the part is absent.
- Readings below the confidence threshold become "needs_review".
- Synthetic observations are refused so they can never leak into a real result.
"""
from typing import Iterable

from backend.app.schemas import ExpectedItem, Finding, Observation, Evidence

DEFAULT_MIN_TEXT_CONFIDENCE = 0.80


def _norm(tag: str) -> str:
    return "".join(ch for ch in tag.upper() if ch.isalnum())


def compare(
    expected: Iterable[ExpectedItem],
    observations_by_image: dict[str, list[Observation]],
    min_text_confidence: float = DEFAULT_MIN_TEXT_CONFIDENCE,
) -> list[Finding]:
    # Build the lookup from the observations passed in on THIS call.
    # The prototype bug: a cache built before detection ran was reused, so new
    # observations never reached this step and every finding was "inconclusive".
    seen: dict[str, list[tuple[str, Observation]]] = {}
    for image_id, observations in observations_by_image.items():
        for obs in observations:
            if obs.source == "synthetic":
                raise ValueError("Synthetic observations must not be used in a real comparison.")
            if obs.kind == "tag_label" and obs.text:
                seen.setdefault(_norm(obs.text), []).append((image_id, obs))

    findings: list[Finding] = []
    expected_tags: set[str] = set()

    for item in expected:
        key = _norm(item.tag)
        expected_tags.add(key)
        hits = seen.get(key, [])
        fid = f"F-{len(findings) + 1:03d}"
        if not hits:
            findings.append(Finding(
                finding_id=fid, type="missing", tag=item.tag, status="inconclusive",
                reason="Tag not read in any photo. Not proof that the part is absent.",
            ))
            continue
        best_image, best = max(hits, key=lambda h: h[1].text_confidence or 0)
        conf = best.text_confidence
        confident = conf is not None and conf >= min_text_confidence
        findings.append(Finding(
            finding_id=fid, type="verified", tag=item.tag,
            observed_text=best.text, ocr_confidence=conf,
            status="verified" if confident else "needs_review",
            reason=None if confident else "Tag read with low confidence.",
            evidence=[Evidence(image_id=img, bbox=o.bbox) for img, o in hits],
        ))

    for key, hits in seen.items():
        if key in expected_tags:
            continue
        image_id, obs = hits[0]
        findings.append(Finding(
            finding_id=f"F-{len(findings) + 1:03d}", type="unexpected", tag=obs.text,
            observed_text=obs.text, ocr_confidence=obs.text_confidence,
            status="needs_review",
            reason="Tag read in photo but not listed in the drawing. Could be an OCR error.",
            evidence=[Evidence(image_id=i, bbox=o.bbox) for i, o in hits],
        ))
    return findings


def overall_status(findings: list[Finding]) -> str:
    statuses = {f.status for f in findings}
    if "potential_mismatch" in statuses:
        return "mismatch_detected"
    if findings and statuses <= {"verified", "confirmed_by_reviewer", "resolved_after_reinspection"}:
        return "pass"
    return "review_required"


def count_by_status(findings: list[Finding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.status] = counts.get(f.status, 0) + 1
    return counts
