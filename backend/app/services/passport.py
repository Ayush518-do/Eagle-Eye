"""Quality passport: the stored history of one cabinet, oldest inspection first.

Everything comes from persisted rows. The current statuses use the same derivation as
`GET /api/inspections/{id}` (services/inspections.py), so the two endpoints cannot disagree. The
engine's original finding status and the overall status it stored are returned next to the
current values, so a reviewer's decision never hides what the engine said.

The passport states what was recorded. It does not say a cabinet is compliant, approved or safe.
"""
from sqlalchemy import literal_column, select
from sqlalchemy.orm import Session

from backend.app import models, schemas
from backend.app.services import inspections as inspection_service


def build_passport(session: Session, cabinet: models.Cabinet) -> schemas.QualityPassport:
    inspections = session.scalars(
        select(models.Inspection).where(models.Inspection.cabinet_id == cabinet.id)
        .order_by(models.Inspection.created_at, literal_column("rowid")))
    return schemas.QualityPassport(
        cabinet_id=cabinet.id, name=cabinet.name,
        inspections=[_inspection_entry(session, i) for i in inspections])


def _inspection_entry(session: Session, inspection: models.Inspection) -> schemas.PassportInspection:
    revision = session.get(models.DesignRevision, inspection.design_revision_id)
    rows = inspection_service.finding_rows(session, inspection.id)
    finding_ids = [f.id for f, _ in rows]
    events = []
    if finding_ids:
        events = session.scalars(select(models.ReviewEvent).where(models.ReviewEvent.finding_id.in_(finding_ids))
                                 .order_by(models.ReviewEvent.created_at, models.ReviewEvent.id))
    return schemas.PassportInspection(
        inspection_id=inspection.id, state=inspection.state, error=inspection.error,
        created_at=inspection.created_at, design_revision_id=revision.label,
        design_revision_internal_id=revision.id, previous_inspection_id=inspection.previous_inspection_id,
        overall_status=inspection_service.current_overall_status(session, inspection),
        engine_overall_status=inspection.overall_status,
        images=[schemas.PassportImage(image_id=i.id, sha256=i.sha256, width=i.width, height=i.height,
                                      quality_flags=i.quality_flags or [])
                for i in inspection_service.images_of(session, inspection.id)],
        findings=[schemas.PassportFinding(finding_id=f.id, type=f.type, tag=f.tag, original_status=f.status,
                                          current_status=current, reason=f.reason) for f, current in rows],
        review_events=[schemas.ReviewEventOut(finding_id=e.finding_id, decision=e.decision, reviewer=e.reviewer,
                                              note=e.note, created_at=e.created_at) for e in events])
