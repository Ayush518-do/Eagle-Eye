"""Reading and running inspections: response building and the background run.

The run reads expected items and observations from the database *inside* the job, on its own
session, never from a list built before the job started (the "everything inconclusive" bug in
docs/team/backend.md). Findings and the final state are written in one transaction.
"""
import logging
from typing import Optional

from sqlalchemy import literal_column, select, update
from sqlalchemy.orm import Session, sessionmaker

from backend.app import models, schemas
from backend.app.ids import new_id
from backend.app.pipeline.compare import compare, overall_status as engine_overall_status
from backend.app.services import alignment as alignment_service
from backend.app.services import status as status_rules
from backend.app.services.expected_items import list_expected_items

log = logging.getLogger(__name__)


# ---------- database rows -> contract models ----------
def expected_item_schema(row: models.ExpectedItem) -> schemas.ExpectedItem:
    rating = None
    if row.rating_source is not None:
        rating = schemas.Rating(value=row.rating_value, source=row.rating_source,
                                page=row.rating_page, needs_review=row.rating_needs_review)
    layout = schemas.Layout(**row.layout) if row.layout else None
    return schemas.ExpectedItem(tag=row.tag, part_number=row.part_number, description=row.description,
                                quantity=row.quantity, rating=rating, source_page=row.source_page,
                                layout=layout)


def observation_schema(row: models.Observation) -> schemas.Observation:
    return schemas.Observation(
        observation_id=row.observation_id, source=row.source, kind=row.kind, class_name=row.class_name,
        bbox=row.bbox, confidence=row.confidence, text=row.text, raw_text=row.raw_text,
        text_confidence=row.text_confidence, model=row.model)


def images_of(session: Session, inspection_id: str) -> list[models.Image]:
    return list(session.scalars(select(models.Image).where(models.Image.inspection_id == inspection_id)
                                .order_by(literal_column("rowid"))))


def observations_of(session: Session, image_id: str) -> list[models.Observation]:
    return list(session.scalars(select(models.Observation).where(models.Observation.image_id == image_id)
                                .order_by(literal_column("rowid"))))


def image_observations(session: Session, image: models.Image) -> schemas.ImageObservations:
    return schemas.ImageObservations(
        image_id=image.id, image_sha256=image.sha256, image_size=(image.width, image.height),
        observations=[observation_schema(o) for o in observations_of(session, image.id)])


# ---------- current status ----------
def finding_rows(session: Session, inspection_id: str) -> list[tuple[models.Finding, str]]:
    """Each finding with its current status (latest review event wins)."""
    findings = list(session.scalars(select(models.Finding).where(models.Finding.inspection_id == inspection_id)
                                    .order_by(literal_column("rowid"))))
    latest: dict[str, str] = {}
    if findings:
        events = session.scalars(select(models.ReviewEvent)
                                 .where(models.ReviewEvent.finding_id.in_([f.id for f in findings]))
                                 .order_by(models.ReviewEvent.id))
        for event in events:  # ascending id, so the last one wins
            latest[event.finding_id] = event.decision
    return [(f, status_rules.current_status(f.status, latest.get(f.id))) for f in findings]


def current_overall_status(session: Session, inspection: models.Inspection) -> Optional[str]:
    if inspection.state != "done":
        return None
    rows = finding_rows(session, inspection.id)
    return status_rules.overall_status([(f.type, f.status, current) for f, current in rows])


def inspection_detail(session: Session, inspection: models.Inspection) -> schemas.InspectionDetail:
    rows = finding_rows(session, inspection.id)
    counts: dict[str, int] = {}
    for _, current in rows:
        counts[current] = counts.get(current, 0) + 1
    revision = session.get(models.DesignRevision, inspection.design_revision_id)
    images = images_of(session, inspection.id)
    expected = list_expected_items(session, inspection.design_revision_id)
    alignments: dict[str, models.ImageAlignment] = {
        a.image_id: a for a in session.scalars(
            select(models.ImageAlignment).where(models.ImageAlignment.image_id.in_([i.id for i in images])))
    } if images else {}
    # Status per tag: used for ghost-box status and for expected_bbox on missing findings.
    status_by_tag = {f.tag: current for f, current in rows if f.tag}
    expected_by_tag = {item.tag: item for item in expected}
    image_infos: list[schemas.ImageInfo] = []
    for i in images:
        alignment = alignments.get(i.id)
        ghost = alignment_service.ghost_boxes_for_image(alignment, expected, status_by_tag) if alignment else []
        image_infos.append(schemas.ImageInfo(
            image_id=i.id, url=f"/api/images/{i.id}", width=i.width, height=i.height,
            quality_flags=i.quality_flags or [],
            alignment_set=alignment is not None,
            ghost=[schemas.GhostBox(**g) for g in ghost],
            is_reference=bool(i.is_reference),
        ))
    finding_schemas: list[schemas.Finding] = []
    for f, current in rows:
        expected_bbox = None
        if f.type == "missing" and f.tag and f.tag in expected_by_tag:
            layout = expected_by_tag[f.tag].layout
            if layout:
                for a in alignments.values():
                    if a.drawing_page == layout.get("page"):
                        projected = alignment_service.project_bbox_drawing_to_photo(a, layout.get("bbox"))
                        if projected:
                            expected_bbox = projected
                            break
        score, sources = _evidence_score(f)
        finding_schemas.append(schemas.Finding(
            finding_id=f.id, type=f.type, tag=f.tag, expected_value=f.expected_value,
            observed_text=f.observed_text, detector_confidence=f.detector_confidence,
            ocr_confidence=f.ocr_confidence, status=current, reason=f.reason,
            evidence=[schemas.Evidence(**e) for e in f.evidence or []],
            expected_bbox=expected_bbox,
            evidence_score=score,
            sources=sources,
        ))
    return schemas.InspectionDetail(
        inspection_id=inspection.id,
        cabinet_id=inspection.cabinet_id,
        # Contract C shows the display label ("REV-A") in design_revision_id.
        design_revision_id=revision.label,
        design_revision_internal_id=revision.id,
        previous_inspection_id=inspection.previous_inspection_id,
        created_at=inspection.created_at,
        overall_status=current_overall_status(session, inspection),
        state=inspection.state,
        error=inspection.error,
        images=image_infos,
        findings=finding_schemas,
        counts=counts,
    )


def _evidence_score(f: models.Finding) -> tuple[Optional[float], list[str]]:
    """Weighted confidence in [0, 1] for a finding, with the contributing source labels.

    - verified: average of OCR + detector confidences, plus a small bonus for cross-source agreement
      and for a second supporting image (each piece of evidence has a distinct image_id when it does).
    - missing: a confidence that the part is really absent; starts at the ratio of inspection images
      that produced any OCR observation, so if the detector covered the cabinet it's higher. Scaled
      by whether an expected_bbox could be projected from the alignment (handled by the caller when
      available; the base term is deliberately conservative).
    - unexpected / rating_mismatch / other: a straight confidence from the engine's own detector/OCR
      scores.
    """
    sources: list[str] = []
    if f.detector_confidence is not None:
        sources.append("detector")
    if f.ocr_confidence is not None:
        sources.append("ocr")
    distinct_images = len({(e or {}).get("image_id") for e in (f.evidence or []) if (e or {}).get("image_id")})
    if distinct_images >= 2:
        sources.append("multi_photo")

    if f.type == "verified":
        parts = [c for c in (f.detector_confidence, f.ocr_confidence) if c is not None]
        base = sum(parts) / len(parts) if parts else 0.75  # tag match without a score is still evidence
        bonus = 0.05 * max(0, len({s for s in sources if s in {"detector", "ocr"}}) - 1)
        bonus += 0.05 if "multi_photo" in sources else 0.0
        return round(min(1.0, base + bonus), 3), sources
    if f.type == "missing":
        # Base: 0.3 (uncertain). Bumps for inconclusive status and for the number of images.
        base = 0.3 + 0.1 * min(distinct_images, 3)
        return round(min(1.0, base), 3), sources or ["coverage"]
    if f.type == "unexpected":
        c = max([x for x in (f.detector_confidence, f.ocr_confidence) if x is not None], default=0.5)
        return round(float(c), 3), sources or ["observation"]
    if f.type == "rating_mismatch":
        c = f.ocr_confidence if f.ocr_confidence is not None else 0.5
        return round(float(c), 3), sources or ["ocr"]
    return None, sources


def _run_detector_on_images(session: Session, inspection_id: str) -> None:
    """Run the trained RF-DETR component detector on every image of the inspection that has
    no detector observations yet.

    Loads the model lazily (first call warms up on the GPU), tile-aware via
    ml.detection.detector.RFDETRDetector. Produces one Contract B observation per
    detection with source='detector', kind='component'. Failures per image are logged, not fatal.
    """
    try:
        from backend.app.config import get_settings
        from backend.app.services.storage import find_upload
    except ImportError:
        return
    settings = get_settings()
    weights = (settings.detector_weights_path or "").strip()
    if not weights:
        log.info("DETECTOR_WEIGHTS_PATH is not set; skipping detector inference.")
        return
    from pathlib import Path as _Path
    weights_path = _Path(weights)
    if not weights_path.exists():
        log.warning("Detector weights not found at %s; skipping detector inference.", weights_path)
        return
    try:
        from PIL import Image, ImageOps
        from ml.detection.detector import RFDETRDetector
    except ImportError as exc:
        log.warning("Detector packages unavailable (%s); skipping detector inference.", exc)
        return
    model_name = settings.detector_model_name or "rf-detr-small"
    try:
        detector = _get_cached_detector(weights_path)
    except Exception as exc:
        log.warning("Could not initialise RF-DETR detector: %s", exc)
        return
    for img in images_of(session, inspection_id):
        already = session.scalars(select(models.Observation).where(
            models.Observation.image_id == img.id, models.Observation.source == "detector").limit(1)).first()
        if already is not None:
            continue
        found = find_upload(settings.upload_dir, img.file_id)
        if found is None:
            log.warning("Image %s file not on disk; skipping detector.", img.id)
            continue
        try:
            pil = ImageOps.exif_transpose(Image.open(found[0])).convert("RGB")
            dets = detector.predict(pil)
        except Exception as exc:
            log.warning("Detector failed on image %s: %s", img.id, exc)
            continue
        log.info("Detector on image %s produced %d component detections.", img.id, len(dets))
        for i, d in enumerate(sorted(dets, key=lambda d: (d["bbox"][1], d["bbox"][0])), start=1):
            try:
                session.add(models.Observation(
                    image_id=img.id,
                    observation_id=f"DET-{img.id}-{i:03d}",
                    source="detector",
                    kind="component",
                    class_name=d.get("class_name") or "mcb",
                    bbox=[round(float(v), 1) for v in d["bbox"]],
                    confidence=round(float(d.get("score") or 0.0), 4),
                    text=None,
                    raw_text=None,
                    text_confidence=None,
                    model={"name": model_name, "version": "eagle-v1", "weights_sha256": None},
                ))
            except Exception as exc:
                log.warning("Could not store detector observation on %s: %s", img.id, exc)
        session.flush()


# Module-level cache so successive inspections re-use the loaded weights (not the SQLAlchemy
# session). Reset when the process restarts.
_DETECTOR_CACHE: dict[str, object] = {}
_ZERO_SHOT_CACHE: dict[tuple, object] = {}


def _get_cached_detector(weights_path):
    """Load (and remember) the trained RF-DETR detector by weights path."""
    key = str(weights_path.resolve())
    cached = _DETECTOR_CACHE.get(key)
    if cached is None:
        from ml.detection.detector import RFDETRDetector
        cached = RFDETRDetector(weights_path, size="small", threshold=0.3)
        _DETECTOR_CACHE[key] = cached
    return cached


def _get_cached_zero_shot(classes: tuple[str, ...], threshold: float):
    """Load (and remember) the OWLv2 zero-shot detector for the given class subset."""
    key = (classes, threshold)
    cached = _ZERO_SHOT_CACHE.get(key)
    if cached is None:
        from ml.detection.zero_shot import OWLv2Detector
        cached = OWLv2Detector(threshold=threshold, classes=list(classes))
        _ZERO_SHOT_CACHE[key] = cached
    return cached


def _run_zero_shot_on_images(session: Session, inspection_id: str) -> None:
    """Run OWLv2 zero-shot detection for the component classes the trained detector
    doesn't cover (power_supply, io_module). Produces Contract B 'component' observations
    with source='zero_shot' and the OWLv2 confidence as `confidence`.

    Threshold is 0.25 (higher precision than the labelling default of 0.15) to limit noise.
    Idempotent per image: images that already have zero_shot observations are skipped.
    Failures per image are logged, not fatal.
    """
    try:
        from backend.app.config import get_settings
        from backend.app.services.storage import find_upload
    except ImportError:
        return
    settings = get_settings()
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        log.warning("Pillow unavailable (%s); skipping zero-shot inference.", exc)
        return
    # The two classes the trained detector was NOT trained on; OWLv2 fills them in.
    zero_shot_classes = ("power_supply", "io_module")
    try:
        model = _get_cached_zero_shot(zero_shot_classes, threshold=0.25)
    except Exception as exc:
        log.warning("Could not initialise OWLv2 zero-shot detector: %s", exc)
        return
    for img in images_of(session, inspection_id):
        already = session.scalars(select(models.Observation).where(
            models.Observation.image_id == img.id, models.Observation.source == "zero_shot").limit(1)).first()
        if already is not None:
            continue
        found = find_upload(settings.upload_dir, img.file_id)
        if found is None:
            log.warning("Image %s file not on disk; skipping zero-shot.", img.id)
            continue
        try:
            pil = ImageOps.exif_transpose(Image.open(found[0])).convert("RGB")
            dets = model.predict(pil)
        except Exception as exc:
            log.warning("OWLv2 zero-shot failed on image %s: %s", img.id, exc)
            continue
        log.info("Zero-shot on image %s produced %d component detections.", img.id, len(dets))
        for i, d in enumerate(sorted(dets, key=lambda d: (d["bbox"][1], d["bbox"][0])), start=1):
            try:
                session.add(models.Observation(
                    image_id=img.id,
                    observation_id=f"ZS-{img.id}-{i:03d}",
                    source="zero_shot",
                    kind="component",
                    class_name=d.get("class_name") or "power_supply",
                    bbox=[round(float(v), 1) for v in d["bbox"]],
                    confidence=round(float(d.get("score") or 0.0), 4),
                    text=None,
                    raw_text=None,
                    text_confidence=None,
                    model={"name": "owlv2-base-patch16-ensemble", "version": "google-apache-2.0",
                           "weights_sha256": None},
                ))
            except Exception as exc:
                log.warning("Could not store zero-shot observation on %s: %s", img.id, exc)
        session.flush()


def _run_ocr_on_images(session: Session, inspection_id: str, expected_tags: list[str]) -> None:
    """Run the OCR tag reader on every image of the inspection that has no ocr observations yet.

    Writes one observation per OCR hit (`source="ocr"`, `kind="tag_label"`). Failures per image are
    logged but do not fail the whole run — the engine simply sees no observations for that image.

    Uses a FAST single-pass path (no tiling, no rotations) so one 4K photo finishes in a few seconds
    instead of several minutes. Small/rotated tags may be missed; that is acceptable for the
    prototype demo. A future wire-up can call the trained RF-DETR + OWLv2 detectors in addition.
    """
    try:
        from PIL import Image, ImageOps
        from backend.app.config import get_settings
        from backend.app.services.storage import find_upload
        from ml.ocr.read_tags import find_tags, clean
        from ml.ocr.tag_matcher import match_tag
    except ImportError as exc:
        log.warning("OCR tag reader unavailable (%s); skipping observation extraction.", exc)
        return
    settings = get_settings()
    expected_clean = [clean(t) for t in (expected_tags or [])]
    for img in images_of(session, inspection_id):
        already = session.scalars(select(models.Observation).where(
            models.Observation.image_id == img.id, models.Observation.source == "ocr").limit(1)).first()
        if already is not None:
            continue  # user or earlier run already produced OCR observations for this image
        found = find_upload(settings.upload_dir, img.file_id)
        if found is None:
            log.warning("Image %s file not on disk; skipping OCR.", img.id)
            continue
        try:
            pil = ImageOps.exif_transpose(Image.open(found[0])).convert("RGB")
            # Fast path: one pass, no tiling, no rotation. Enough for upright close-up tag stickers.
            tile = max(pil.width, pil.height)
            tags = find_tags(pil, expected_clean or None, tile=tile, overlap=0.0, rotations=(0,))
            result = {
                "observations": [{
                    "observation_id": f"OCR-{img.id}-{i:03d}",
                    "source": "ocr",
                    "kind": "tag_label",
                    "class_name": "tag_label",
                    "bbox": [round(float(v), 1) for v in t["bbox"]],
                    "confidence": None,
                    "text": t["tag"],
                    "raw_text": t["raw"],
                    "text_confidence": round(float(t["score"]), 4),
                    "model": {"name": "rapidocr-onnxruntime", "version": None, "weights_sha256": None},
                } for i, t in enumerate(sorted(tags, key=lambda t: (t["bbox"][1], t["bbox"][0])), start=1)],
            }
        except Exception as exc:
            log.warning("OCR failed on image %s: %s", img.id, exc)
            continue
        log.info("OCR on image %s found %d tag observations.", img.id, len(result.get("observations") or []))
        for o in result.get("observations") or []:
            try:
                session.add(models.Observation(
                    image_id=img.id,
                    observation_id=o["observation_id"],
                    source=o.get("source") or "ocr",
                    kind=o.get("kind") or "tag_label",
                    class_name=o.get("class_name") or "tag_label",
                    bbox=o["bbox"],
                    confidence=o.get("confidence"),
                    text=o.get("text"),
                    raw_text=o.get("raw_text"),
                    text_confidence=o.get("text_confidence"),
                    model=o.get("model"),
                ))
            except Exception as exc:
                log.warning("Could not store OCR observation on %s: %s", img.id, exc)
        session.flush()


# ---------- the run ----------
def run_inspection_job(factory: sessionmaker[Session], inspection_id: str) -> None:
    """Background task. The endpoint has already set the state to `running`.

    Steps:
    1) Run the trained RF-DETR component detector on every image to produce 'component' observations
       for the classes the detector was trained on (mcb). Needs DETECTOR_WEIGHTS_PATH to point at a
       readable .pth file; silently skipped otherwise.
    2) Run the OWLv2 zero-shot detector for classes the trained model doesn't cover
       (power_supply, io_module). Threshold 0.25 for precision. Idempotent per image.
    3) Run the OCR tag reader on every image to produce tag_label observations
       (unless OCR observations are already stored for that image, e.g. from a previous run or a
       manual upload). Failures per image are logged, not fatal.
    4) Build Contract B observation lists per image and run the comparison engine.
    5) Save findings and mark the inspection done. Any uncaught exception marks the run failed.
    """
    with factory() as session:
        try:
            inspection = session.get(models.Inspection, inspection_id)
            expected = [expected_item_schema(r) for r in list_expected_items(session, inspection.design_revision_id)]
            _run_detector_on_images(session, inspection_id)
            _run_zero_shot_on_images(session, inspection_id)
            _run_ocr_on_images(session, inspection_id, [e.tag for e in expected])
            by_image = {img.id: [observation_schema(o) for o in observations_of(session, img.id)]
                        for img in images_of(session, inspection_id)}
            findings = compare(expected, by_image)
            for f in findings:
                session.add(models.Finding(
                    id=new_id("F"), inspection_id=inspection_id, type=f.type, tag=f.tag,
                    expected_value=f.expected_value, observed_text=f.observed_text,
                    detector_confidence=f.detector_confidence, ocr_confidence=f.ocr_confidence,
                    status=f.status, reason=f.reason, evidence=[e.model_dump() for e in f.evidence]))
            inspection.overall_status = engine_overall_status(findings)  # engine-time outcome
            inspection.error = None
            inspection.state = "done"
            session.commit()
        except Exception as exc:  # the run must end in `failed`, not hang in `running`
            session.rollback()
            log.exception("Inspection %s failed", inspection_id)
            # ValueError carries our own plain messages; anything else is not shown to the client.
            message = str(exc) if isinstance(exc, ValueError) else f"Unexpected {type(exc).__name__}; see the server log."
            session.execute(update(models.Inspection).where(models.Inspection.id == inspection_id)
                            .values(state="failed", error=message))
            session.commit()
