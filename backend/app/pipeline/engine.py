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
    """Lower verified findings when all supporting photos are blurry."""
    del thresholds  # Comparison already applies the configured OCR threshold.
    gated: list[Finding] = []
    for finding in findings:
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
    return findings, image_flags
