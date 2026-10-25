"""Inspections, observations, runs, images, review and reinspection (docs/team/backend.md
endpoints 6-12). The quality passport (13) is in api/cabinets.py with the other cabinet reads."""
from pathlib import PurePosixPath, PureWindowsPath
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app import models, schemas
from backend.app.config import Settings, get_settings
from backend.app.db import get_db, get_session_factory
from backend.app.services import inspections as inspection_service
from backend.app.services.images import QUALITY_NOT_MEASURED, image_size
from backend.app.services.storage import UploadRejected, detect_type, find_upload, remove_upload, save_upload

router = APIRouter(tags=["inspections"])

MIN_PHOTOS, MAX_PHOTOS = 1, 10
EDITABLE_STATES = ("queued", "failed")  # a done or running inspection no longer takes new inputs


def get_inspection_or_404(db: Session, inspection_id: str) -> models.Inspection:
    inspection = db.get(models.Inspection, inspection_id)
    if inspection is None:
        raise HTTPException(404, "Inspection not found.")
    return inspection


def _safe_name(upload: UploadFile) -> str:
    return PureWindowsPath(PurePosixPath(upload.filename or "photo").name).name[:80]


# 6
@router.post("/cabinets/{cabinet_id}/inspections", response_model=schemas.InspectionAccepted, status_code=202)
async def create_inspection(
    cabinet_id: str,
    design_revision_id: str = Form(...),
    photos: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> schemas.InspectionAccepted:
    if db.get(models.Cabinet, cabinet_id) is None:
        raise HTTPException(404, "Cabinet not found.")
    revision = db.get(models.DesignRevision, design_revision_id)
    if revision is None or revision.cabinet_id != cabinet_id:
        raise HTTPException(404, "Design revision not found for this cabinet.")
    if not MIN_PHOTOS <= len(photos) <= MAX_PHOTOS:
        raise HTTPException(400, f"Upload between {MIN_PHOTOS} and {MAX_PHOTOS} photos; got {len(photos)}.")

    checked = await _read_photos(photos, settings)
    inspection = _store_inspection(db, settings, cabinet_id, revision.id, checked)
    return schemas.InspectionAccepted(inspection_id=inspection.id, state=inspection.state)


async def _read_photos(photos: list[UploadFile], settings: Settings) -> list[tuple[UploadFile, bytes, tuple[int, int]]]:
    """Check every photo before saving any, so a bad one leaves no files behind."""
    limit = settings.max_upload_mb * 1024 * 1024
    checked: list[tuple[UploadFile, bytes, tuple[int, int]]] = []
    for number, photo in enumerate(photos, start=1):
        data = await photo.read(limit + 1)
        where = f'Photo {number} ("{_safe_name(photo)}")'
        try:
            if not data:
                raise UploadRejected("The file is empty.")
            if len(data) > limit:
                raise UploadRejected(f"The file is larger than the {settings.max_upload_mb} MB limit.")
            content_type = detect_type(data[:16])[0]
            if content_type not in ("image/jpeg", "image/png"):
                raise UploadRejected("Only JPEG and PNG photos are accepted.")
            checked.append((photo, data, image_size(data, content_type)))
        except UploadRejected as exc:
            raise HTTPException(400, f"{where}: {exc}") from None
    return checked


def _store_inspection(
    db: Session, settings: Settings, cabinet_id: str, revision_id: str, checked: list,
    previous_id: str | None = None,
) -> models.Inspection:
    """Save the photos and the inspection together; on any failure no row and no file remains."""
    saved: list[dict] = []
    try:
        if previous_id is not None:
            _claim_reinspection_slot(db, previous_id)
        inspection = models.Inspection(cabinet_id=cabinet_id, design_revision_id=revision_id,
                                       previous_inspection_id=previous_id)
        db.add(inspection)
        db.flush()
        for photo, data, (width, height) in checked:
            meta = save_upload(data, photo.filename or "photo", settings.upload_dir, settings.max_upload_mb)
            saved.append(meta)
            db.add(models.Image(inspection_id=inspection.id, file_id=meta["file_id"], sha256=meta["sha256"],
                                width=width, height=height, quality_flags=[QUALITY_NOT_MEASURED]))
        db.commit()
    except UploadRejected as exc:
        db.rollback()
        _remove_all(settings, saved)
        raise HTTPException(400, str(exc)) from exc
    except Exception:
        db.rollback()
        _remove_all(settings, saved)
        raise
    return inspection


def _claim_reinspection_slot(db: Session, previous_id: str) -> None:
    """Allow one open (queued or running) reinspection per inspection at a time.

    The no-op UPDATE takes SQLite's write lock first, so two simultaneous requests are handled one
    after the other and the second one sees the first one's row. The caller's rollback releases it."""
    db.execute(update(models.Inspection).where(models.Inspection.id == previous_id)
               .values(id=models.Inspection.id))
    open_child = db.scalars(select(models.Inspection.id).where(
        models.Inspection.previous_inspection_id == previous_id,
        models.Inspection.state.in_(("queued", "running"))).limit(1)).first()
    if open_child:
        raise HTTPException(409, f"Inspection {open_child} is already waiting to be reinspected or running; "
                                 "finish or fail it before starting another reinspection.")


# 12
@router.post("/inspections/{inspection_id}/reinspection", response_model=schemas.ReinspectionAccepted,
             status_code=202)
async def create_reinspection(
    inspection_id: str,
    photos: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> schemas.ReinspectionAccepted:
    """A new inspection of the same cabinet and design revision, linked to `inspection_id`.

    The earlier inspection, its findings and its review events are not touched. The new inspection
    starts `queued`; it gets observations and a run like any other (endpoints 7 and 8)."""
    previous = get_inspection_or_404(db, inspection_id)
    if previous.state != "done":
        raise HTTPException(409, f"Only a completed inspection can be reinspected; this one is {previous.state}.")
    if not MIN_PHOTOS <= len(photos) <= MAX_PHOTOS:
        raise HTTPException(400, f"Upload between {MIN_PHOTOS} and {MAX_PHOTOS} photos; got {len(photos)}.")
    checked = await _read_photos(photos, settings)
    inspection = _store_inspection(db, settings, previous.cabinet_id, previous.design_revision_id, checked,
                                   previous_id=previous.id)
    return schemas.ReinspectionAccepted(inspection_id=inspection.id, state=inspection.state,
                                        previous_inspection_id=previous.id)


def _remove_all(settings: Settings, saved: list[dict]) -> None:
    for meta in saved:
        remove_upload(settings.upload_dir, meta["file_id"])


# 7
@router.post("/inspections/{inspection_id}/observations", response_model=schemas.ImageObservations, status_code=201)
def add_observations(
    inspection_id: str, body: schemas.ImageObservations, db: Session = Depends(get_db)
) -> schemas.ImageObservations:
    inspection = get_inspection_or_404(db, inspection_id)
    if body.contract_version != schemas.CONTRACT_VERSION:
        raise HTTPException(400, f"Unsupported contract_version {body.contract_version!r}; "
                                 f"this server supports {schemas.CONTRACT_VERSION!r}.")
    image = db.get(models.Image, body.image_id)
    if image is None or image.inspection_id != inspection.id:
        raise HTTPException(404, "Image not found in this inspection.")
    if inspection.state not in EDITABLE_STATES:
        raise HTTPException(409, f"Observations cannot be added while the inspection is {inspection.state}.")
    if body.image_sha256 is not None and body.image_sha256.lower() != image.sha256.lower():
        raise HTTPException(409, "image_sha256 does not match the stored image.")
    if tuple(body.image_size) != (image.width, image.height):
        raise HTTPException(409, f"image_size does not match the stored image ({image.width} x {image.height}).")

    ids = [o.observation_id.strip() for o in body.observations]
    if any(not i for i in ids):
        raise HTTPException(400, "observation_id must not be blank.")
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    if repeated:
        raise HTTPException(400, "Duplicate observation_id in this request: " + ", ".join(repeated) + ".")
    for o in body.observations:
        # Contract B: coordinates are pixels of the original image. `not (a <= b)` also rejects NaN.
        x1, y1, x2, y2 = o.bbox
        if not (0 <= x1 and 0 <= y1 and x2 <= image.width and y2 <= image.height):
            raise HTTPException(400, f"bbox of observation {o.observation_id.strip()!r} lies outside the "
                                     f"image ({image.width} x {image.height} pixels).")
    not_manual = sorted({o.observation_id for o in body.observations if o.source != "manual"})
    if not_manual:
        raise HTTPException(400, 'Only observations with source "manual" can be posted here; '
                                 "detector and OCR observations come from the pipeline.")
    stored = set(db.scalars(select(models.Observation.observation_id).where(
        models.Observation.image_id == image.id, models.Observation.observation_id.in_(ids))))
    if stored:
        raise HTTPException(409, "Observation already stored for this image: " + ", ".join(sorted(stored)) + ".")

    for o, observation_id in zip(body.observations, ids):
        db.add(models.Observation(
            image_id=image.id, observation_id=observation_id, source=o.source, kind=o.kind,
            class_name=o.class_name, bbox=o.bbox, confidence=o.confidence, text=o.text, raw_text=o.raw_text,
            text_confidence=o.text_confidence, model=o.model.model_dump() if o.model else None))
    try:
        db.commit()
    except IntegrityError:  # the unique (image_id, observation_id) constraint caught a concurrent request
        db.rollback()
        raise HTTPException(409, "An observation with one of these ids was stored by another request.") from None
    return inspection_service.image_observations(db, image)


# extra (not in the numbered list): read the stored observations, one Contract B block per image
@router.get("/inspections/{inspection_id}/observations", response_model=list[schemas.ImageObservations])
def list_observations(inspection_id: str, db: Session = Depends(get_db)) -> list[schemas.ImageObservations]:
    inspection = get_inspection_or_404(db, inspection_id)
    return [inspection_service.image_observations(db, i) for i in inspection_service.images_of(db, inspection.id)]


# 8
@router.post("/inspections/{inspection_id}/run", response_model=schemas.InspectionAccepted, status_code=202)
def run_inspection(
    inspection_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    factory: sessionmaker[Session] = Depends(get_session_factory),
) -> schemas.InspectionAccepted:
    inspection = get_inspection_or_404(db, inspection_id)
    state = inspection.state
    # One atomic statement, so two requests cannot both start the same run.
    started = db.execute(update(models.Inspection).where(
        models.Inspection.id == inspection_id, models.Inspection.state.in_(EDITABLE_STATES)
    ).values(state="running", error=None))
    if started.rowcount != 1:
        db.rollback()
        raise HTTPException(409, f"The inspection is already {state}.")
    db.commit()
    background.add_task(inspection_service.run_inspection_job, factory, inspection_id)
    return schemas.InspectionAccepted(inspection_id=inspection_id, state="running")


# 9
@router.get("/inspections/{inspection_id}", response_model=schemas.InspectionDetail)
def get_inspection(inspection_id: str, db: Session = Depends(get_db)) -> schemas.InspectionDetail:
    return inspection_service.inspection_detail(db, get_inspection_or_404(db, inspection_id))


# 10
@router.get("/images/{image_id}")
def get_image(
    image_id: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> FileResponse:
    image = db.get(models.Image, image_id)
    found = find_upload(settings.upload_dir, image.file_id) if image else None
    if found is None:
        raise HTTPException(404, "Image not found.")
    path, media_type = found
    return FileResponse(path, media_type=media_type, headers={"X-Content-Type-Options": "nosniff"})


# 11
@router.post("/findings/{finding_id}/review", response_model=schemas.ReviewEventOut, status_code=201)
def review_finding(
    finding_id: str, body: schemas.ReviewDecision, db: Session = Depends(get_db)
) -> schemas.ReviewEventOut:
    finding = db.get(models.Finding, finding_id)
    if finding is None:
        raise HTTPException(404, "Finding not found.")
    reviewer = body.reviewer.strip()
    if not reviewer:
        raise HTTPException(400, "The reviewer name must not be blank.")
    event = models.ReviewEvent(finding_id=finding.id, decision=body.decision, reviewer=reviewer, note=body.note)
    db.add(event)  # insert only: review history is never updated or deleted
    db.commit()
    return schemas.ReviewEventOut(finding_id=event.finding_id, decision=event.decision, reviewer=event.reviewer,
                                  note=event.note, created_at=event.created_at)


# 14
@router.get(
    "/inspections/{inspection_id}/findings/{finding_id}/fit-feasibility",
    response_model=schemas.EmptyPositionFitReportOut,
)
def get_finding_fit_feasibility(
    inspection_id: str, finding_id: str, db: Session = Depends(get_db)
) -> schemas.EmptyPositionFitReportOut:
    """Assess mechanical and physical fit feasibility for a missing or replacement component."""
    inspection = get_inspection_or_404(db, inspection_id)
    finding = db.get(models.Finding, finding_id)
    if finding is None or finding.inspection_id != inspection.id:
        raise HTTPException(404, "Finding not found for this inspection.")

    expected_item = None
    if finding.tag:
        expected_item = db.scalars(
            select(models.ExpectedItem).where(
                models.ExpectedItem.design_revision_id == inspection.design_revision_id,
                models.ExpectedItem.tag == finding.tag,
            )
        ).first()

    images = inspection_service.images_of(db, inspection.id)
    flags = [flag for img in images for flag in (img.quality_flags or [])]

    from dataclasses import asdict
    from backend.app.pipeline.fit_feasibility import assess_empty_position

    tag_str = finding.tag or "UNKNOWN"
    part_number = expected_item.part_number if expected_item else None
    rating_str = expected_item.rating_value if expected_item else finding.expected_value

    report = assess_empty_position(
        finding_id=finding.id,
        tag=tag_str,
        component_type="mcb",
        expected_part_number=part_number,
        expected_rating_str=rating_str,
        image_flags=flags,
    )
    return schemas.EmptyPositionFitReportOut(**asdict(report))


# 19 (Contract D)
@router.get("/analytics", response_model=schemas.AnalyticsOut, tags=["analytics"])
def get_analytics(
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
) -> schemas.AnalyticsOut:
    return inspection_service.compute_analytics(db, from_date=from_date, to_date=to_date)
