"""Cabinets, design revisions and expected items (docs/team/backend.md endpoints 1-5).

Every endpoint uses the request's session and commits explicitly after it has validated and
stored everything; an error leaves nothing committed (the session is rolled back on close).
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app import models, schemas
from backend.app.config import Settings, get_settings
from backend.app.db import get_db
from backend.app.services import inspections as inspection_service
from backend.app.services import passport as passport_service
from backend.app.services.expected_items import (
    ExpectedItemsError, list_expected_items, replace_from_submission,
)
from backend.app.services.pdf import check_pdf
from backend.app.services.storage import UploadRejected, detect_type, remove_upload, save_upload

router = APIRouter(tags=["cabinets"])


def get_cabinet_or_404(db: Session, cabinet_id: str) -> models.Cabinet:
    cabinet = db.get(models.Cabinet, cabinet_id)
    if cabinet is None:
        raise HTTPException(404, "Cabinet not found.")
    return cabinet


def get_revision_or_404(db: Session, revision_id: str) -> models.DesignRevision:
    revision = db.get(models.DesignRevision, revision_id)
    if revision is None:
        raise HTTPException(404, "Design revision not found.")
    return revision


def revision_out(r: models.DesignRevision) -> schemas.DesignRevisionOut:
    return schemas.DesignRevisionOut(
        design_revision_id=r.id, cabinet_id=r.cabinet_id, label=r.label,
        drawing_sha256=r.drawing_sha256, parser_version=r.parser_version, created_at=r.created_at)


# 1
@router.post("/cabinets", response_model=schemas.CabinetOut, status_code=201)
def create_cabinet(body: schemas.CabinetCreate, db: Session = Depends(get_db)) -> schemas.CabinetOut:
    if db.get(models.Cabinet, body.cabinet_id) is not None:
        raise HTTPException(409, f"Cabinet {body.cabinet_id} already exists.")
    cabinet = models.Cabinet(id=body.cabinet_id, name=body.name)
    db.add(cabinet)
    try:
        db.commit()
    except IntegrityError:  # a concurrent request created the same id
        db.rollback()
        raise HTTPException(409, f"Cabinet {body.cabinet_id} already exists.") from None
    return schemas.CabinetOut(cabinet_id=cabinet.id, name=cabinet.name, created_at=cabinet.created_at)


# 2
@router.get("/cabinets", response_model=list[schemas.CabinetSummary])
def list_cabinets(db: Session = Depends(get_db)) -> list[schemas.CabinetSummary]:
    out = []
    for c in db.scalars(select(models.Cabinet).order_by(models.Cabinet.created_at, models.Cabinet.id)):
        latest = db.scalars(select(models.Inspection).where(models.Inspection.cabinet_id == c.id)
                            .order_by(models.Inspection.created_at.desc(), models.Inspection.id.desc())
                            .limit(1)).first()
        out.append(schemas.CabinetSummary(
            cabinet_id=c.id, name=c.name, created_at=c.created_at,
            latest_inspection_id=latest.id if latest else None,
            latest_inspection_state=latest.state if latest else None,
            latest_overall_status=inspection_service.current_overall_status(db, latest) if latest else None))
    return out


# 3
@router.get("/cabinets/{cabinet_id}", response_model=schemas.CabinetDetail)
def get_cabinet(cabinet_id: str, db: Session = Depends(get_db)) -> schemas.CabinetDetail:
    c = get_cabinet_or_404(db, cabinet_id)
    revisions = db.scalars(select(models.DesignRevision).where(models.DesignRevision.cabinet_id == c.id)
                           .order_by(models.DesignRevision.created_at, models.DesignRevision.id))
    return schemas.CabinetDetail(cabinet_id=c.id, name=c.name, created_at=c.created_at,
                                 design_revisions=[revision_out(r) for r in revisions])


# 13
@router.get("/cabinets/{cabinet_id}/quality-passport", response_model=schemas.QualityPassport)
def quality_passport(cabinet_id: str, db: Session = Depends(get_db)) -> schemas.QualityPassport:
    return passport_service.build_passport(db, get_cabinet_or_404(db, cabinet_id))


# 4
@router.post("/cabinets/{cabinet_id}/design-revisions", response_model=schemas.DesignRevisionOut,
             status_code=201)
async def create_design_revision(
    cabinet_id: str,
    label: str = Form(...),
    drawing: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> schemas.DesignRevisionOut:
    cabinet = get_cabinet_or_404(db, cabinet_id)
    label = label.strip()
    if not label or len(label) > 100:
        raise HTTPException(400, "The label must be 1 to 100 characters, for example REV-A.")

    limit = settings.max_upload_mb * 1024 * 1024
    data = await drawing.read(limit + 1)
    try:
        if data and detect_type(data[:16])[0] != "application/pdf":
            raise UploadRejected("The drawing must be a PDF file.")
        if data:
            check_pdf(data)
        meta = save_upload(data, drawing.filename or "drawing.pdf", settings.upload_dir, settings.max_upload_mb)
    except UploadRejected as exc:
        raise HTTPException(400, str(exc)) from exc

    revision = models.DesignRevision(cabinet_id=cabinet.id, label=label, drawing_file_id=meta["file_id"],
                                     drawing_sha256=meta["sha256"])
    try:
        db.add(revision)
        db.commit()
    except Exception:
        db.rollback()
        remove_upload(settings.upload_dir, meta["file_id"])  # no orphan file for a failed write
        raise
    return revision_out(revision)


# 5
@router.post("/design-revisions/{revision_id}/expected-items", response_model=schemas.ExpectedItemsSubmission,
             status_code=201)
def replace_expected_items(
    revision_id: str, body: schemas.ExpectedItemsSubmission, db: Session = Depends(get_db)
) -> schemas.ExpectedItemsSubmission:
    try:
        replace_from_submission(db, revision_id, body)
        db.commit()
    except ExpectedItemsError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.detail) from None
    except Exception:
        db.rollback()
        raise
    return _expected_items_out(db, get_revision_or_404(db, revision_id))


# extra (not in the numbered list): read back the stored items, in the same Contract A shape
@router.get("/design-revisions/{revision_id}/expected-items", response_model=schemas.ExpectedItemsSubmission)
def get_expected_items(revision_id: str, db: Session = Depends(get_db)) -> schemas.ExpectedItemsSubmission:
    return _expected_items_out(db, get_revision_or_404(db, revision_id))


def _expected_items_out(db: Session, revision: models.DesignRevision) -> schemas.ExpectedItemsSubmission:
    return schemas.ExpectedItemsSubmission(
        drawing_file_sha256=revision.drawing_sha256, parser_version=revision.parser_version,
        items=[inspection_service.expected_item_schema(r) for r in list_expected_items(db, revision.id)])
