"""Single entry point for a cabinet inspection."""
from collections.abc import Mapping
import math
from typing import Any

from pydantic import BaseModel, ValidationError
from PIL import Image, UnidentifiedImageError

from backend.app.pipeline.compare import compare
from backend.app.pipeline.image_quality import check_photo
from backend.app.pipeline.reinspection import compare_with_previous
from backend.app.pipeline.thresholds import load_thresholds
from backend.app.schemas import (
    CONTRACT_VERSION,
    DrawingParseResult,
    Finding,
    ImageObservations,
)


Thresholds = dict[str, Any] | None

# The available detector producer emits contract B as 0.3. Its observation
# fields remain compatible with the engine's v0.2 schema; unknown additions
# are still rejected below.
SUPPORTED_IMAGE_CONTRACT_VERSIONS = frozenset({CONTRACT_VERSION, "0.3"})


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


def _reject_unknown_contract_fields(payload: Any, model: type[BaseModel], context: str) -> None:
    """Reject producer fields Pydantic would otherwise silently ignore."""
    if not isinstance(payload, Mapping):
        return
    unknown = set(payload) - set(model.model_fields)
    if unknown:
        names = ", ".join(sorted(str(name) for name in unknown))
        raise ValueError(f"{context} contains unsupported field(s): {names}")
    for name, field in model.model_fields.items():
        if name not in payload:
            continue
        annotation = field.annotation
        nested_models = _nested_model_types(annotation)
        if not nested_models:
            continue
        value = payload[name]
        if isinstance(value, list):
            for index, entry in enumerate(value):
                for nested_model in nested_models:
                    if isinstance(entry, Mapping):
                        _reject_unknown_contract_fields(
                            entry, nested_model, f"{context}.{name}[{index}]"
                        )
        elif isinstance(value, Mapping):
            _reject_unknown_contract_fields(
                value, nested_models[0], f"{context}.{name}"
            )


def _nested_model_types(annotation: Any) -> list[type[BaseModel]]:
    """Find model types inside Optional/list annotations for strict input checks."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    found: list[type[BaseModel]] = []
    for argument in getattr(annotation, "__args__", ()):
        found.extend(_nested_model_types(argument))
    return found


def _validate_producer_contract(
    payload: Any,
    model: type[BaseModel],
    context: str,
    supported_versions: frozenset[str] | None = None,
):
    if not isinstance(payload, Mapping):
        raise TypeError(f"{context} must be a mapping")
    versions = supported_versions or frozenset({CONTRACT_VERSION})
    if payload.get("contract_version") not in versions:
        expected = ", ".join(repr(version) for version in sorted(versions))
        raise ValueError(
            f"{context}.contract_version must be one of: {expected}"
        )
    _reject_unknown_contract_fields(payload, model, context)
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid {context} contract: {exc}") from exc


def _validate_declared_image_size(payload: Mapping[str, Any], image_id: str, path) -> None:
    """Ensure contract B dimensions describe the original image on disk."""
    raw_size = payload.get("image_size")
    if (
        not isinstance(raw_size, (list, tuple))
        or len(raw_size) != 2
        or any(type(value) is not int or value <= 0 for value in raw_size)
    ):
        raise ValueError(
            f"Image contract for {image_id!r} image_size must contain two positive integers"
        )
    try:
        with Image.open(path) as image:
            image.load()
            actual_size = (image.width, image.height)
    except (FileNotFoundError, IsADirectoryError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError(f"Unable to read image path for contract image {image_id!r}") from exc
    if tuple(raw_size) != actual_size:
        raise ValueError(
            f"Image contract for {image_id!r} declares size {tuple(raw_size)!r}, "
            f"but the original image is {actual_size!r}"
        )


def run_inspection_from_contracts(
    drawing_contract,
    image_contracts_by_id,
    image_paths,
    thresholds=None,
):
    """Validate producer contract dictionaries and adapt them for the engine.

    ``image_paths`` may contain additional uploaded images with no observations;
    their photo-quality flags are still assessed by :func:`run_inspection`.
    """
    drawing = _validate_producer_contract(
        drawing_contract, DrawingParseResult, "drawing contract"
    )
    if not drawing.parser_version.strip():
        raise ValueError("drawing contract parser_version must be non-empty")
    if any(not item.tag.strip() for item in drawing.items):
        raise ValueError("drawing contract expected item tags must be non-empty")
    if not isinstance(image_paths, Mapping):
        raise TypeError("image_paths must map image IDs to local image paths")
    if not isinstance(image_contracts_by_id, Mapping):
        raise TypeError("image_contracts_by_id must map image IDs to contract B mappings")

    observations_by_image = {}
    for image_id, payload in image_contracts_by_id.items():
        context = f"image contract for {image_id!r}"
        image = _validate_producer_contract(
            payload,
            ImageObservations,
            context,
            SUPPORTED_IMAGE_CONTRACT_VERSIONS,
        )
        if not isinstance(image_id, str) or not image_id.strip():
            raise ValueError("image contract mapping keys must be non-empty image IDs")
        if image.image_id != image_id:
            raise ValueError(
                f"{context} declares image_id {image.image_id!r}, which does not match its mapping key"
            )
        if image_id not in image_paths:
            raise ValueError(f"{context} has no corresponding entry in image_paths")
        _validate_declared_image_size(payload, image_id, image_paths[image_id])
        width, height = image.image_size
        observation_ids = [observation.observation_id for observation in image.observations]
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError(f"{context} observation IDs must be unique within the image")
        for observation in image.observations:
            if not observation.observation_id.strip():
                raise ValueError(f"{context} observation IDs must be non-empty")
            if any(not math.isfinite(value) for value in observation.bbox):
                raise ValueError(f"{context} observation {observation.observation_id!r} has non-finite bbox coordinates")
            x_min, y_min, x_max, y_max = observation.bbox
            if x_min < 0 or y_min < 0 or x_max > width or y_max > height:
                raise ValueError(
                    f"{context} observation {observation.observation_id!r} bbox falls outside image_size"
                )
        observations_by_image[image_id] = image.observations

    return run_inspection(
        drawing.items, observations_by_image, image_paths, thresholds
    )


def run_reinspection(
    previous_findings,
    expected_items,
    observations_by_image,
    image_paths,
    thresholds=None,
):
    """Run a new inspection and preserve/resolve findings from its predecessor.

    This pipeline-level entry point leaves ``run_inspection`` unchanged. The API
    layer can supply the prior inspection's findings and store the returned
    combined findings on the new inspection.
    """
    new_findings, image_flags = run_inspection(
        expected_items,
        observations_by_image,
        image_paths,
        thresholds,
    )
    return compare_with_previous(
        previous_findings,
        new_findings,
        assessed_image_ids=set(image_flags),
    ), image_flags
