"""Single entry point for a cabinet inspection."""
from typing import Any

from backend.app.pipeline.compare import compare
from backend.app.pipeline.image_quality import check_photo
from backend.app.pipeline.thresholds import load_thresholds
from backend.app.schemas import Finding


Thresholds = dict[str, Any] | None


def apply_confidence_gate(
    findings: list[Finding],
    image_flags: dict[str, list[str]],
    thresholds: Thresholds = None,
) -> list[Finding]:
    """Lower certainty when evidence quality or reading confidence is insufficient."""
    settings = load_thresholds(thresholds)
    gated: list[Finding] = []
    for finding in findings:
        if (
            finding.status == "potential_mismatch"
            and (
                finding.ocr_confidence is None
                or finding.ocr_confidence < settings["min_text_confidence"]
            )
        ):
            gated.append(finding.model_copy(update={
                "status": "needs_review",
                "reason": "Potential mismatch read with low confidence.",
            }))
            continue

        evidence_image_ids = [evidence.image_id for evidence in finding.evidence]
        evidence_unassessed = not evidence_image_ids or any(
            image_id not in image_flags for image_id in evidence_image_ids
        )
        all_evidence_blurry = not evidence_unassessed and all(
            "low_sharpness" in image_flags.get(image_id, [])
            for image_id in evidence_image_ids
        )
        if finding.status == "verified" and evidence_unassessed:
            gated.append(finding.model_copy(update={
                "status": "needs_review",
                "reason": "Evidence photo quality could not be assessed.",
            }))
        elif finding.status == "verified" and all_evidence_blurry:
            gated.append(finding.model_copy(update={
                "status": "needs_review",
                "reason": "Supporting photo may be blurry.",
            }))
        else:
            gated.append(finding)
    return gated


def _apply_expected_item_rules(findings, expected_items, observations_by_image):
    """Apply Step 4 rules that need the expected item and per-image readings."""
    readings_by_tag: dict[str, dict[str, str]] = {}
    for image_id, observations in observations_by_image.items():
        for observation in observations:
            if observation.kind != "tag_label" or not observation.text:
                continue
            key = _normalise_tag(observation.text)
            reading = observation.raw_text or observation.text
            readings_by_tag.setdefault(key, {})[image_id] = reading

    updated = list(findings)
    changed = False
    for item in expected_items:
        key = _normalise_tag(item.tag)
        matching = [
            finding for finding in updated
            if _normalise_tag(getattr(finding, "tag", None) or "") == key
        ]
        if not matching:
            continue

        readings = readings_by_tag.get(key, {})
        distinct_readings_by_key = {}
        for reading in readings.values():
            cleaned = reading.strip()
            if cleaned:
                distinct_readings_by_key.setdefault(_normalise_tag(cleaned), cleaned)
        distinct_readings = list(distinct_readings_by_key.values())
        conflict_reason = None
        if len(readings) > 1 and len(distinct_readings) > 1:
            conflict_reason = (
                "Photos contain conflicting readings for this tag: "
                + "; ".join(f'"{reading}"' for reading in distinct_readings)
                + "."
            )

        rating_reason = None
        if item.rating is not None and item.rating.needs_review:
            rating_reason = "Rating check skipped because the expected rating needs review."

        for finding in matching:
            reasons = [
                reason for reason in (finding.reason, conflict_reason, rating_reason)
                if reason
            ]
            if not reasons:
                continue
            reason = " ".join(dict.fromkeys(reasons))
            update = {"reason": reason}
            if conflict_reason:
                update["status"] = "needs_review"
            updated[updated.index(finding)] = finding.model_copy(update=update)
            changed = True
    return updated if changed else findings


def _normalise_tag(tag: str) -> str:
    return "".join(character for character in tag.upper() if character.isalnum())


def run_inspection(
    expected_items,
    observations_by_image,
    image_paths,
    thresholds=None,
):
    """Return ``(findings, image_flags)`` for the supplied inspection inputs."""
    settings = load_thresholds(thresholds)
    image_flags = {
        image_id: check_photo(path, settings)
        for image_id, path in image_paths.items()
    }
    findings = compare(
        expected_items,
        observations_by_image,
        min_text_confidence=settings["min_text_confidence"],
    )
    findings = apply_confidence_gate(findings, image_flags, settings)
    findings = _apply_expected_item_rules(
        findings, expected_items, observations_by_image
    )
    return findings, image_flags
