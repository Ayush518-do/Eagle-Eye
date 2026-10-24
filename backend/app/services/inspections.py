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
from backend.app.services import status as status_rules
from backend.app.services.expected_items import list_expected_items

log = logging.getLogger(__name__)


# ---------- database rows -> contract models ----------
def expected_item_schema(row: models.ExpectedItem) -> schemas.ExpectedItem:
    rating = None
    if row.rating_source is not None:
        rating = schemas.Rating(value=row.rating_value, source=row.rating_source,
                                page=row.rating_page, needs_review=row.rating_needs_review)
    return schemas.ExpectedItem(tag=row.tag, part_number=row.part_number, description=row.description,
                                quantity=row.quantity, rating=rating, source_page=row.source_page)


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
        images=[schemas.ImageInfo(image_id=i.id, url=f"/api/images/{i.id}", width=i.width, height=i.height,
                                  quality_flags=i.quality_flags or []) for i in images_of(session, inspection.id)],
        findings=[schemas.Finding(
            finding_id=f.id, type=f.type, tag=f.tag, expected_value=f.expected_value,
            observed_text=f.observed_text, detector_confidence=f.detector_confidence,
            ocr_confidence=f.ocr_confidence, status=current, reason=f.reason,
            evidence=[schemas.Evidence(**e) for e in f.evidence or []]) for f, current in rows],
        counts=counts,
    )


# ---------- the run ----------
def run_inspection_job(factory: sessionmaker[Session], inspection_id: str) -> None:
    """Background task. The endpoint has already set the state to `running`.

    Uses `compare()` until the engine team provides `run_inspection` (docs/team/backend.md,
    Step 3). Starter limits: it matches tags only, so it produces no rating findings.
    """
    with factory() as session:
        try:
            inspection = session.get(models.Inspection, inspection_id)
            expected = [expected_item_schema(r) for r in list_expected_items(session, inspection.design_revision_id)]
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
