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
        finding_schemas.append(schemas.Finding(
            finding_id=f.id, type=f.type, tag=f.tag, expected_value=f.expected_value,
            observed_text=f.observed_text, detector_confidence=f.detector_confidence,
            ocr_confidence=f.ocr_confidence, status=current, reason=f.reason,
            evidence=[schemas.Evidence(**e) for e in f.evidence or []],
            expected_bbox=expected_bbox,
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
    1) Run the OCR tag reader on every image of the inspection to produce tag_label observations
       (unless OCR observations are already stored for that image, e.g. from a previous run or a
       manual upload). Failures per image are logged, not fatal.
    2) Build Contract B observation lists per image and run the comparison engine.
    3) Save findings and mark the inspection done. Any uncaught exception marks the run failed.
    """
    with factory() as session:
        try:
            inspection = session.get(models.Inspection, inspection_id)
            expected = [expected_item_schema(r) for r in list_expected_items(session, inspection.design_revision_id)]
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
