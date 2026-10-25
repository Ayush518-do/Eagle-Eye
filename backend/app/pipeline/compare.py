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


def _center(b: list[float]) -> tuple[float, float]:
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def _covers(outer: list[float], inner_center: tuple[float, float]) -> bool:
    """Does the (expanded) outer bbox contain the inner_center?"""
    pad_x = (outer[2] - outer[0]) * 0.2
    pad_y = (outer[3] - outer[1]) * 0.2
    cx, cy = inner_center
    return (outer[0] - pad_x) <= cx <= (outer[2] + pad_x) and (outer[1] - pad_y) <= cy <= (outer[3] + pad_y)


def _best_component_match(
    tag_obs: Observation,
    components_by_image: dict[str, list[Observation]],
    image_id: str,
) -> Observation | None:
    """Of the component observations on the same image, pick the one whose box covers the
    tag label's centre with the highest confidence. None if nothing covers it."""
    best = None
    best_conf = -1.0
    tag_center = _center(tag_obs.bbox)
    for comp in components_by_image.get(image_id, []):
        if _covers(comp.bbox, tag_center):
            c = comp.confidence or 0.0
            if c > best_conf:
                best = comp
                best_conf = c
    return best


def compare(
    expected: Iterable[ExpectedItem],
    observations_by_image: dict[str, list[Observation]],
    min_text_confidence: float = DEFAULT_MIN_TEXT_CONFIDENCE,
) -> list[Finding]:
    # Build the lookup from the observations passed in on THIS call.
    # The prototype bug: a cache built before detection ran was reused, so new
    # observations never reached this step and every finding was "inconclusive".
    seen: dict[str, list[tuple[str, Observation]]] = {}
    components_by_image: dict[str, list[Observation]] = {}
    ratings_by_image: dict[str, list[Observation]] = {}
    for image_id, observations in observations_by_image.items():
        for obs in observations:
            if obs.source == "synthetic":
                raise ValueError("Synthetic observations must not be used in a real comparison.")
            if obs.kind == "tag_label" and obs.text:
                seen.setdefault(_norm(obs.text), []).append((image_id, obs))
            elif obs.kind == "rating" and (obs.text or obs.raw_text):
                ratings_by_image.setdefault(image_id, []).append(obs)
            elif obs.kind == "component":
                components_by_image.setdefault(image_id, []).append(obs)

    findings: list[Finding] = []
    expected_tags: set[str] = set()

    from backend.app.pipeline.rating_format import normalise_rating

    for item in expected:
        key = _norm(item.tag)
        expected_tags.add(key)
        hits = seen.get(key, [])
        fid = f"F-{len(findings) + 1:03d}"
        exp_rating = item.rating.value if item.rating else None
        if not hits:
            findings.append(Finding(
                finding_id=fid, type="missing", tag=item.tag, status="inconclusive",
                expected_value=exp_rating,
                reason="Tag not read in any photo. Not proof that the part is absent.",
            ))
            continue
        best_image, best = max(hits, key=lambda h: h[1].text_confidence or 0)
        conf = best.text_confidence
        confident = conf is not None and conf >= min_text_confidence

        # Bind detector / zero_shot component observations whose bbox covers this tag label.
        evidence = [Evidence(image_id=img, bbox=o.bbox, source=o.source) for img, o in hits]
        det_conf = None
        matched_comp = None
        for img, tag_obs in hits:
            comp = _best_component_match(tag_obs, components_by_image, img)
            if comp is not None:
                evidence.append(Evidence(image_id=img, bbox=comp.bbox, source=comp.source))
                if det_conf is None or (comp.confidence or 0.0) > det_conf:
                    det_conf = comp.confidence
                    matched_comp = comp

        # Check for matching or mismatched rating on the same image
        observed_rating = None
        rating_match_obs = None
        for r_obs in ratings_by_image.get(best_image, []):
            r_center = _center(r_obs.bbox)
            if matched_comp and _covers(matched_comp.bbox, r_center):
                rating_match_obs = r_obs
                break

        if rating_match_obs is not None:
            observed_rating = rating_match_obs.text or rating_match_obs.raw_text
            evidence.append(Evidence(image_id=best_image, bbox=rating_match_obs.bbox, source=rating_match_obs.source))

        # Determine finding type and status
        f_type = "verified"
        f_status = "verified" if confident else "needs_review"
        f_reason = None if confident else "Tag read with low confidence."
        observed_display = best.text

        if exp_rating and observed_rating:
            p_exp = normalise_rating(exp_rating)
            p_obs = normalise_rating(observed_rating)
            if p_exp and p_obs and p_exp != p_obs:
                f_type = "rating_mismatch"
                f_status = "potential_mismatch"
                f_reason = f"Rating on the component ({observed_rating}) differs from the drawing ({exp_rating})."
                observed_display = f"{best.text} ({observed_rating})"
            elif p_exp and p_obs and p_exp == p_obs:
                observed_display = f"{best.text} ({observed_rating})"

        # Check component type if matched
        expected_type = None
        t_upper = item.tag.upper()
        if t_upper.startswith("CB") or t_upper.startswith("DS"):
            expected_type = "mcb"
        elif t_upper.startswith("PS"):
            expected_type = "power_supply"
        elif t_upper.startswith("IO"):
            expected_type = "io_module"

        if matched_comp and expected_type and matched_comp.class_name:
            if matched_comp.class_name != expected_type and (matched_comp.confidence or 0.0) >= 0.70 and f_type == "verified":
                f_type = "type_mismatch"
                f_status = "potential_mismatch"
                f_reason = f"Observed component ({matched_comp.class_name}) differs from expected tag type ({expected_type})."

        findings.append(Finding(
            finding_id=fid, type=f_type, tag=item.tag,
            expected_value=exp_rating,
            observed_text=observed_display, ocr_confidence=conf,
            detector_confidence=det_conf,
            status=f_status,
            reason=f_reason,
            evidence=evidence,
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
            evidence=[Evidence(image_id=i, bbox=o.bbox, source=o.source) for i, o in hits],
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
