"""Threshold-independent helpers for the documented rating formats.

The inspection entry point deliberately does not call these association helpers
until a calibrated distance threshold has been approved.
"""
from dataclasses import dataclass
import math
from collections.abc import Mapping, Sequence
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from backend.app.pipeline.rating_format import normalise_rating
from backend.app.schemas import ExpectedItem, Finding, Observation, Evidence


_ATTESTATION_ISSUER = object()


@dataclass(frozen=True, init=False)
class CallerAttestedRatingDistanceThreshold:
    """Distance threshold supplied under an explicit caller attestation.

    This records the caller's assertion and is not evidence that calibration or
    review occurred. No production calibration-record mechanism exists yet.
    Instances must come from :func:`attest_rating_distance_threshold`; a raw
    float is never accepted by the comparison helper.
    """

    value: float
    attestation_reference: str

    def __init__(
        self,
        value: float,
        attestation_reference: str,
        *,
        _issuer: object | None = None,
    ) -> None:
        if _issuer is not _ATTESTATION_ISSUER:
            raise TypeError("Use attest_rating_distance_threshold() to create a caller-attested threshold")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Caller-attested rating distance threshold must be numeric")
        value = float(value)
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Caller-attested rating distance threshold must be finite and between 0 and 1")
        if not isinstance(attestation_reference, str) or not attestation_reference.strip():
            raise ValueError("An explicit attestation reference is required")
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "attestation_reference", attestation_reference.strip())


def attest_rating_distance_threshold(
    value: float,
    *,
    attestation_reference: str,
) -> CallerAttestedRatingDistanceThreshold:
    """Record caller attestation only; this does not verify calibration or review."""
    return CallerAttestedRatingDistanceThreshold(
        value,
        attestation_reference,
        _issuer=_ATTESTATION_ISSUER,
    )


@dataclass(frozen=True)
class RatingCandidate:
    """A nearest expected-tag candidate; it carries no approval decision."""

    tag: str
    image_id: str
    observation: Observation
    distance_fraction: float
    ambiguous: bool


@dataclass(frozen=True)
class RatingComparison:
    """Comparison outcome without introducing a new public finding status."""

    finding: Finding | None = None
    review_reason: str | None = None


def read_image_dimensions(
    image_paths: Mapping[str, str | Path],
) -> dict[str, tuple[int, int] | None]:
    """Read dimensions safely; unavailable or invalid files have no dimensions."""
    dimensions: dict[str, tuple[int, int] | None] = {}
    for image_id, path in image_paths.items():
        try:
            with Image.open(path) as image:
                width, height = image.size
                dimensions[image_id] = (width, height) if width > 0 and height > 0 else None
        except (FileNotFoundError, IsADirectoryError, UnidentifiedImageError, OSError, ValueError):
            dimensions[image_id] = None
    return dimensions


def normalized_center_distance(
    first_bbox: Sequence[float],
    second_bbox: Sequence[float],
    image_size: tuple[int, int],
) -> float | None:
    """Return center distance divided by image diagonal, or None for invalid input."""
    if len(first_bbox) != 4 or len(second_bbox) != 4:
        return None
    width, height = image_size
    if width <= 0 or height <= 0:
        return None
    diagonal = math.hypot(width, height)
    if diagonal == 0 or not math.isfinite(diagonal):
        return None
    try:
        x1 = (float(first_bbox[0]) + float(first_bbox[2])) / 2
        y1 = (float(first_bbox[1]) + float(first_bbox[3])) / 2
        x2 = (float(second_bbox[0]) + float(second_bbox[2])) / 2
        y2 = (float(second_bbox[1]) + float(second_bbox[3])) / 2
        distance = math.hypot(x1 - x2, y1 - y2) / diagonal
    except (TypeError, ValueError, OverflowError):
        return None
    return distance if math.isfinite(distance) else None


def associate_rating_candidates(
    expected_items: Sequence[ExpectedItem],
    observations_by_image: Mapping[str, Sequence[Observation]],
    image_dimensions: Mapping[str, tuple[int, int] | None],
) -> list[RatingCandidate]:
    """Find nearest expected tag boxes without approving their proximity.

    Tag observations are matched to expected items by normalized text. A tie is
    retained as ambiguous instead of selecting a candidate arbitrarily. The
    result only carries measured distances; approval belongs to comparison.
    """
    expected_by_key = {_normalise_tag(item.tag): item.tag for item in expected_items}
    candidates: list[RatingCandidate] = []
    for image_id, observations in observations_by_image.items():
        size = image_dimensions.get(image_id)
        if size is None:
            continue
        tags: list[tuple[str, Observation]] = []
        ratings: list[Observation] = []
        for observation in observations:
            if observation.kind == "tag_label" and observation.text:
                tag = expected_by_key.get(_normalise_tag(observation.text))
                if tag is not None:
                    tags.append((tag, observation))
            elif observation.kind == "rating":
                ratings.append(observation)

        for rating in ratings:
            distance_by_tag: dict[str, float] = {}
            for tag, tag_obs in tags:
                distance = normalized_center_distance(rating.bbox, tag_obs.bbox, size)
                if distance is not None:
                    distance_by_tag[tag] = min(distance, distance_by_tag.get(tag, math.inf))
            distances = list(distance_by_tag.items())
            if not distances:
                continue
            nearest_distance = min(distance for _, distance in distances)
            nearest = [(tag, distance) for tag, distance in distances if distance == nearest_distance]
            is_ambiguous = len(nearest) > 1
            for tag, distance in nearest:
                candidates.append(RatingCandidate(
                    tag=tag,
                    image_id=image_id,
                    observation=rating,
                    distance_fraction=distance,
                    ambiguous=is_ambiguous,
                ))
    return candidates


def compare_rating_candidates(
    expected_item: ExpectedItem,
    candidates: Sequence[RatingCandidate],
    finding_id: str,
    min_text_confidence: float,
    *,
    attested_threshold: CallerAttestedRatingDistanceThreshold | None = None,
) -> RatingComparison:
    """Compare readings only with an explicit caller-attested distance limit.

    The inspection entry point does not supply this value: production rating
    mismatch generation stays disabled until a reviewed calibration mechanism
    is established.
    """
    if attested_threshold is not None and not isinstance(
        attested_threshold, CallerAttestedRatingDistanceThreshold
    ):
        raise TypeError("attested_threshold must be created by attest_rating_distance_threshold()")
    expected_rating = expected_item.rating
    if expected_rating is None or expected_rating.needs_review:
        return RatingComparison(review_reason="Expected rating is absent or needs review; rating check skipped.")
    expected = normalise_rating(expected_rating.value)
    if expected is None:
        return RatingComparison(review_reason="Expected rating is unparseable; rating check skipped.")

    relevant = [candidate for candidate in candidates if candidate.tag == expected_item.tag]
    if attested_threshold is None:
        return RatingComparison()
    accepted = [
        candidate for candidate in relevant
        if candidate.distance_fraction <= attested_threshold.value
    ]
    if not accepted:
        return RatingComparison()
    if any(candidate.ambiguous for candidate in accepted):
        return RatingComparison(review_reason="Rating is equally close to multiple expected tags; association needs review.")

    parsed = [(candidate, normalise_rating(candidate.observation.raw_text)) for candidate in accepted]
    if any(value is None for _, value in parsed):
        return RatingComparison(review_reason="An associated rating is unreadable or unparseable; mismatch not asserted.")
    parsed = [(candidate, value) for candidate, value in parsed if value is not None]
    if not parsed:
        return RatingComparison()
    values = {value for _, value in parsed}
    if len(values) > 1:
        return RatingComparison(review_reason="Conflicting rating readings are associated with this tag; rating check needs review.")
    observed = parsed[0][1]
    if observed == expected:
        return RatingComparison()

    # A repeated reading is one result. Use the weakest available OCR confidence
    # so duplicates cannot make the finding appear more certain.
    confidences = [candidate.observation.text_confidence for candidate, _ in parsed]
    confidence = None if any(value is None for value in confidences) else min(confidences)
    status = (
        "potential_mismatch"
        if confidence is not None and confidence >= min_text_confidence
        else "needs_review"
    )
    reason = None if status == "potential_mismatch" else "Rating mismatch read with low or unavailable confidence."
    unique_evidence = {}
    for candidate, _ in parsed:
        observation = candidate.observation
        unique_evidence[(candidate.image_id, tuple(observation.bbox))] = Evidence(
            image_id=candidate.image_id,
            bbox=observation.bbox,
        )
    return RatingComparison(finding=Finding(
        finding_id=finding_id,
        type="rating_mismatch",
        tag=expected_item.tag,
        expected_value=expected_rating.value,
        observed_text=parsed[0][0].observation.raw_text,
        ocr_confidence=confidence,
        status=status,
        reason=reason,
        evidence=list(unique_evidence.values()),
    ))


def _normalise_tag(tag: str) -> str:
    return "".join(character for character in tag.upper() if character.isalnum())
