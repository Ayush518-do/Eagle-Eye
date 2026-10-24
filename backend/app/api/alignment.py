"""Ghost overlay endpoints (Contract E) + export endpoints the frontend expects.

- `GET/PUT/DELETE /api/images/{image_id}/alignment` — per-image 4-point alignment.
- `GET /api/design-revisions/{id}/drawing-pages/{page}.png?width=2000` — rendered PDF page as PNG;
  sets `X-Page-Size: 1191x842` so the frontend can convert click pixels to PDF points.
- `GET /api/inspections/{id}/export.csv` — findings as CSV, for the report download.
- `GET /api/inspections/{id}/report` — a minimal HTML report. A richer PDF is out of scope here.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.app import models, schemas
from backend.app.config import Settings, get_settings
from backend.app.db import get_db
from backend.app.services import alignment as alignment_service
from backend.app.services import inspections as inspection_service
from backend.app.services import visual_compare as visual_compare_service
from backend.app.services.storage import find_upload

router = APIRouter(tags=["alignment"])


# ---------- Alignment (Contract E) ----------
def _get_image_or_404(db: Session, image_id: str) -> models.Image:
    image = db.get(models.Image, image_id)
    if image is None:
        raise HTTPException(404, "Image not found.")
    return image


@router.get("/images/{image_id}/alignment", response_model=schemas.AlignmentOut)
def get_alignment(image_id: str, db: Session = Depends(get_db)) -> schemas.AlignmentOut:
    _get_image_or_404(db, image_id)
    row = db.get(models.ImageAlignment, image_id)
    if row is None:
        raise HTTPException(404, "No alignment saved for this image.")
    return schemas.AlignmentOut(
        image_id=row.image_id, drawing_page=row.drawing_page,
        drawing_points=row.drawing_points, photo_points=row.photo_points,
        created_at=row.created_at, updated_at=row.updated_at,
    )


@router.put("/images/{image_id}/alignment", response_model=schemas.AlignmentOut)
def put_alignment(
    image_id: str, body: schemas.AlignmentIn, db: Session = Depends(get_db)
) -> schemas.AlignmentOut:
    _get_image_or_404(db, image_id)
    try:
        drawing_pts = alignment_service.validate_points(body.drawing_points, "drawing_points")
        photo_pts = alignment_service.validate_points(body.photo_points, "photo_points")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    now = datetime.now(timezone.utc)
    row = db.get(models.ImageAlignment, image_id)
    if row is None:
        row = models.ImageAlignment(
            image_id=image_id, drawing_page=body.drawing_page,
            drawing_points=drawing_pts, photo_points=photo_pts,
            created_at=now, updated_at=now,
        )
        db.add(row)
    else:
        row.drawing_page = body.drawing_page
        row.drawing_points = drawing_pts
        row.photo_points = photo_pts
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return schemas.AlignmentOut(
        image_id=row.image_id, drawing_page=row.drawing_page,
        drawing_points=row.drawing_points, photo_points=row.photo_points,
        created_at=row.created_at, updated_at=row.updated_at,
    )


@router.delete("/images/{image_id}/alignment", status_code=204)
def delete_alignment(image_id: str, db: Session = Depends(get_db)) -> Response:
    _get_image_or_404(db, image_id)
    row = db.get(models.ImageAlignment, image_id)
    if row is not None:
        db.delete(row)
        db.commit()
    return Response(status_code=204)


# ---------- Drawing page PNG ----------
@router.get("/design-revisions/{revision_id}/drawing-pages/{page}.png")
def drawing_page_png(
    revision_id: str, page: int, width: int = 2000,
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> Response:
    revision = db.get(models.DesignRevision, revision_id)
    if revision is None:
        raise HTTPException(404, "Design revision not found.")
    if page < 1:
        raise HTTPException(400, "page must be 1 or more.")
    width = max(200, min(width, 4000))
    found = find_upload(settings.upload_dir, revision.drawing_file_id)
    if found is None:
        raise HTTPException(404, "Drawing file not found on disk.")
    path, _ = found
    pdf_bytes = path.read_bytes()
    try:
        png, (w_pts, h_pts) = alignment_service.render_drawing_page_png(pdf_bytes, page, width)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:  # pragma: no cover — any pdfium failure is a 500
        raise HTTPException(500, f"Could not render drawing page: {exc!s}") from exc
    return Response(
        content=png,
        media_type="image/png",
        headers={"X-Page-Size": f"{w_pts:.0f}x{h_pts:.0f}"},
    )


# ---------- Visual compare: reference-vs-candidate change regions ----------
@router.get("/images/{candidate_image_id}/visual-compare")
def visual_compare(
    candidate_image_id: str,
    reference: str,  # the OTHER image id to compare against (query param: ?reference=IMG-...)
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Run SIFT + homography diff between an approved REFERENCE photo and this candidate.

    Returns the regions-of-change as bboxes in the CANDIDATE's original pixel space, each
    with an area fraction and a change_score in [0, 1]. Reviewers can overlay these on
    the candidate photo as a "Change regions" layer.
    """
    cand = db.get(models.Image, candidate_image_id)
    ref = db.get(models.Image, reference)
    if cand is None or ref is None:
        raise HTTPException(404, "One of the images was not found.")
    cand_found = find_upload(settings.upload_dir, cand.file_id)
    ref_found = find_upload(settings.upload_dir, ref.file_id)
    if cand_found is None or ref_found is None:
        raise HTTPException(404, "One of the image files is missing on disk.")
    try:
        from pathlib import Path as _Path
        result = visual_compare_service.compare_images(_Path(ref_found[0]), _Path(cand_found[0]))
    except ImportError as exc:
        raise HTTPException(503, f"Visual compare unavailable: {exc!s}") from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(422, f"Compare failed: {exc!s}") from exc
    return {
        "candidate_image_id": candidate_image_id,
        "reference_image_id": reference,
        **result,
    }


# ---------- Export: CSV ----------
def _csv_text(detail: schemas.InspectionDetail) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "finding_id", "type", "tag", "status", "expected_value", "observed_text",
        "detector_confidence", "ocr_confidence", "reason",
    ])
    for f in detail.findings:
        writer.writerow([
            f.finding_id, f.type, f.tag or "", f.status, f.expected_value or "", f.observed_text or "",
            "" if f.detector_confidence is None else f"{f.detector_confidence:.3f}",
            "" if f.ocr_confidence is None else f"{f.ocr_confidence:.3f}",
            f.reason or "",
        ])
    return buf.getvalue()


@router.get("/inspections/{inspection_id}/export.csv")
def export_inspection_csv(inspection_id: str, db: Session = Depends(get_db)) -> Response:
    inspection = db.get(models.Inspection, inspection_id)
    if inspection is None:
        raise HTTPException(404, "Inspection not found.")
    detail = inspection_service.inspection_detail(db, inspection)
    return Response(
        content=_csv_text(detail),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="inspection-{inspection_id}.csv"'},
    )


# ---------- Export: HTML report ----------
_REPORT_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Eagle Eye inspection {inspection_id}</title>
<style>
  body {{ font: 14px/1.4 -apple-system, Segoe UI, system-ui, sans-serif; color: #0a1930; margin: 2rem; }}
  h1 {{ margin: 0 0 0.25rem 0; font-size: 1.4rem; }}
  .meta {{ color: #566; margin-bottom: 1.5rem; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.9rem; }}
  th, td {{ border: 1px solid #d0d7de; padding: 6px 8px; text-align: left; vertical-align: top; }}
  th {{ background: #f6f7f9; }}
  .counts {{ margin: 1rem 0; }}
  .counts span {{ margin-right: 1rem; }}
  .pill {{ display: inline-block; padding: 2px 8px; border-radius: 10px;
            background: #eef1f4; color: #0a1930; font-size: 0.78rem; }}
</style></head>
<body>
<h1>Inspection {inspection_id}</h1>
<div class="meta">Cabinet {cabinet_id} — Revision {design_revision_id} — {created_at}</div>
<div class="counts">Overall: <span class="pill">{overall_status}</span>{count_pills}</div>
<table><thead><tr>
<th>Tag</th><th>Type</th><th>Status</th><th>Expected</th><th>Observed</th><th>Reason</th>
</tr></thead><tbody>
{rows}
</tbody></table>
<p style="color:#999;font-size:0.75rem">Generated by Eagle Eye prototype. Not for safety or compliance sign-off.</p>
</body></html>
"""


@router.get("/inspections/{inspection_id}/report")
def inspection_report_html(inspection_id: str, db: Session = Depends(get_db)) -> Response:
    inspection = db.get(models.Inspection, inspection_id)
    if inspection is None:
        raise HTTPException(404, "Inspection not found.")
    detail = inspection_service.inspection_detail(db, inspection)
    count_pills = "".join(
        f'<span class="pill">{k}: {v}</span>' for k, v in sorted(detail.counts.items())
    )
    rows = "".join(
        f"<tr><td>{(f.tag or '').replace('<','&lt;')}</td>"
        f"<td>{f.type}</td><td>{f.status}</td>"
        f"<td>{(f.expected_value or '').replace('<','&lt;')}</td>"
        f"<td>{(f.observed_text or '').replace('<','&lt;')}</td>"
        f"<td>{(f.reason or '').replace('<','&lt;')}</td></tr>"
        for f in detail.findings
    )
    html = _REPORT_TEMPLATE.format(
        inspection_id=detail.inspection_id,
        cabinet_id=detail.cabinet_id,
        design_revision_id=detail.design_revision_id or "",
        created_at=detail.created_at.isoformat(),
        overall_status=detail.overall_status or "pending",
        count_pills=count_pills,
        rows=rows or '<tr><td colspan="6" style="text-align:center;color:#999;">No findings yet.</td></tr>',
    )
    return Response(
        content=html,
        media_type="text/html",
        headers={"Content-Disposition": f'inline; filename="inspection-{inspection_id}.html"'},
    )
