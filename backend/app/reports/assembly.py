"""Assemble an API-supplied inspection envelope for report rendering.

The service layer owns inspection/cabinet identity, creation time, authorized
image URLs, trusted storage paths, and any prior image records referenced by a
reinspection. This adapter derives only current image dimensions, counts, and
overall status; it never invents or exposes local paths.
"""

from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError

from backend.app.pipeline.compare import count_by_status, overall_status
from backend.app.schemas import Finding, ImageInfo, InspectionResult


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be a non-empty string without surrounding whitespace")
    return value


def _image_dimensions(path: str | Path, image_id: str) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
    except (FileNotFoundError, IsADirectoryError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError(f"Unable to read trusted image path for {image_id!r}") from exc
    if width <= 0 or height <= 0:
        raise ValueError(f"Image dimensions for {image_id!r} must be positive")
    return width, height


def _authorized_image_url(value: str, image_id: str) -> str:
    value = _required_text(value, f"image_urls[{image_id!r}]")
    if any(ord(character) < 32 or ord(character) == 127 for character in value) or "\\" in value:
        raise ValueError(f"image_urls[{image_id!r}] contains unsafe URL characters")
    parsed = urlsplit(value)
    safe_relative_path = value.startswith("/") and not value.startswith("//")
    safe_absolute_url = (
        parsed.scheme.lower() in {"http", "https"}
        and bool(parsed.netloc)
        and parsed.username is None
        and parsed.password is None
    )
    if not (safe_relative_path or safe_absolute_url):
        raise ValueError(
            f"image_urls[{image_id!r}] must be a service-authorized relative path or HTTP(S) URL"
        )
    return value


def assemble_inspection_result(
    *,
    inspection_id: str,
    cabinet_id: str,
    created_at: datetime,
    findings: Iterable[Finding],
    image_flags: Mapping[str, list[str]],
    image_paths: Mapping[str, str | Path],
    image_urls: Mapping[str, str],
    design_revision_id: str | None = None,
    prior_images: Iterable[ImageInfo] = (),
) -> InspectionResult:
    """Build an ``InspectionResult`` from engine output and required service metadata.

    ``image_paths`` must be trusted local paths to the original uploaded photos,
    and ``image_urls`` must be the service-authorized URLs for those image IDs.
    For reinspection, ``prior_images`` supplies persisted image records needed
    by evidence retained from earlier findings.
    """
    inspection_id = _required_text(inspection_id, "inspection_id")
    cabinet_id = _required_text(cabinet_id, "cabinet_id")
    if not isinstance(created_at, datetime):
        raise TypeError("created_at must be supplied as a datetime by the service layer")
    if design_revision_id is not None:
        design_revision_id = _required_text(design_revision_id, "design_revision_id")
    if not isinstance(image_flags, Mapping):
        raise TypeError("image_flags must be a mapping from image IDs to quality flags")
    if not isinstance(image_paths, Mapping):
        raise TypeError("image_paths must be a mapping of trusted image IDs to local paths")
    if not isinstance(image_urls, Mapping):
        raise TypeError("image_urls must be a mapping of image IDs to authorized URLs")

    current_ids = set(image_flags)
    if set(image_paths) != current_ids:
        raise ValueError("image_paths IDs must exactly match image_flags IDs")
    if set(image_urls) != current_ids:
        raise ValueError("image_urls IDs must exactly match image_flags IDs")

    current_images: list[ImageInfo] = []
    for image_id, flags in image_flags.items():
        _required_text(image_id, "image ID")
        if not isinstance(flags, list) or any(not isinstance(flag, str) for flag in flags):
            raise ValueError(f"Quality flags for {image_id!r} must be a list of strings")
        url = _authorized_image_url(image_urls[image_id], image_id)
        width, height = _image_dimensions(image_paths[image_id], image_id)
        current_images.append(ImageInfo(
            image_id=image_id,
            url=url,
            width=width,
            height=height,
            quality_flags=list(flags),
        ))

    historical_images = list(prior_images)
    if any(not isinstance(image, ImageInfo) for image in historical_images):
        raise TypeError("prior_images must contain validated ImageInfo objects")
    for image in historical_images:
        _required_text(image.image_id, "prior image ID")
        _authorized_image_url(image.url, image.image_id)
        if image.width <= 0 or image.height <= 0:
            raise ValueError(f"Prior image dimensions for {image.image_id!r} must be positive")
    all_images = current_images + historical_images
    image_ids = [image.image_id for image in all_images]
    if len(image_ids) != len(set(image_ids)):
        raise ValueError("Current and prior image records must have unique image IDs")

    result_findings = list(findings)
    if any(not isinstance(finding, Finding) for finding in result_findings):
        raise TypeError("findings must contain validated Finding objects")
    finding_ids = [finding.finding_id for finding in result_findings]
    if len(finding_ids) != len(set(finding_ids)):
        raise ValueError("findings must have unique finding_id values")
    known_image_ids = set(image_ids)
    dangling_evidence = {
        evidence.image_id
        for finding in result_findings
        for evidence in finding.evidence
        if evidence.image_id not in known_image_ids
    }
    if dangling_evidence:
        raise ValueError(
            "Evidence references image IDs without supplied image records: "
            + ", ".join(sorted(dangling_evidence))
        )

    return InspectionResult(
        inspection_id=inspection_id,
        cabinet_id=cabinet_id,
        design_revision_id=design_revision_id,
        created_at=created_at,
        overall_status=overall_status(result_findings),
        images=all_images,
        findings=result_findings,
        counts=count_by_status(result_findings),
    )
