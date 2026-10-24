"""Render a self-contained HTML inspection report using local dependencies.

The report uses Python's standard library and Pillow, which is already a
backend dependency. Text is escaped and evidence crops are embedded as PNG data
URIs, so the resulting file contains no references to local image paths.

The task specification calls for Jinja2. This renderer currently avoids adding
or installing that dependency; the template-engine requirement remains a
documented deviation pending dependency approval.
"""

import base64
from collections.abc import Mapping
from datetime import datetime
from html import escape
import io
import math
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from backend.app.pipeline.compare import overall_status
from backend.app.schemas import Finding, InspectionResult


_STATUS_LABELS = {
    "verified": "Verified",
    "potential_mismatch": "Potential mismatch",
    "needs_review": "Needs review",
    "inconclusive": "Inconclusive",
    "confirmed_by_reviewer": "Confirmed by reviewer",
    "rejected_by_reviewer": "Rejected by reviewer",
    "resolved_after_reinspection": "Resolved after reinspection",
}
_QUALITY_LABELS = {
    "low_resolution": "Photo resolution is below the configured threshold.",
    "low_sharpness": "Photo may be blurry.",
    "overexposed": "Glare or overexposure may hide details.",
}
def _safe_overall_status(inspection: InspectionResult) -> str:
    """Derive status from current findings, ignoring stale caller metadata."""
    return overall_status(inspection.findings)


def _crop_data_uri(
    image_path: str | Path | None,
    bbox: list[float],
) -> str | None:
    if image_path is None:
        return None
    try:
        with Image.open(image_path) as source:
            left = max(0, min(source.width, math.floor(bbox[0])))
            top = max(0, min(source.height, math.floor(bbox[1])))
            right = max(0, min(source.width, math.ceil(bbox[2])))
            bottom = max(0, min(source.height, math.ceil(bbox[3])))
            if right <= left or bottom <= top:
                return None
            crop = source.crop((left, top, right, bottom)).convert("RGB")
            crop.thumbnail((640, 480))
            buffer = io.BytesIO()
            crop.save(buffer, format="PNG")
    except (OSError, ValueError, TypeError, UnidentifiedImageError):
        return None
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _evidence_markup(
    finding: Finding,
    image_paths: Mapping[str, str | Path],
    known_image_ids: set[str],
) -> str:
    if not finding.evidence:
        return '<span class="muted">No evidence attached.</span>'
    blocks = []
    for evidence in finding.evidence:
        image_id = escape(evidence.image_id, quote=True)
        image_path = (
            image_paths.get(evidence.image_id)
            if evidence.image_id in known_image_ids
            else None
        )
        data_uri = _crop_data_uri(image_path, evidence.bbox)
        if data_uri is None:
            content = '<span class="muted">Evidence image unavailable.</span>'
        else:
            content = (
                f'<img alt="Evidence crop for {image_id}" '
                f'src="{data_uri}" loading="lazy">'
            )
        blocks.append(
            f'<figure class="evidence"><figcaption>{image_id}</figcaption>{content}</figure>'
        )
    return "".join(blocks)


def render_html_report(
    inspection: InspectionResult,
    image_paths: Mapping[str, str | Path],
) -> str:
    """Return a complete, escaped HTML report for one inspection."""
    status = _safe_overall_status(inspection)
    created_at = inspection.created_at
    if isinstance(created_at, datetime):
        created_text = created_at.isoformat()
    else:
        created_text = str(created_at)

    image_sections = []
    for image in inspection.images:
        flags = [
            _QUALITY_LABELS.get(flag, f"Quality flag: {flag}")
            for flag in image.quality_flags
        ]
        flag_markup = (
            "<ul>" + "".join(f"<li>{escape(flag)}</li>" for flag in flags) + "</ul>"
            if flags
            else '<p class="muted">No photo-quality flags.</p>'
        )
        image_sections.append(
            '<section class="photo"><h3>Photo '
            f"{escape(image.image_id)}</h3><p>{image.width} × {image.height} pixels</p>"
            f"{flag_markup}</section>"
        )

    if inspection.findings:
        rows = []
        for finding in inspection.findings:
            confidence = finding.ocr_confidence
            confidence_text = "—"
            if (
                confidence is not None
                and math.isfinite(confidence)
                and 0 <= confidence <= 1
            ):
                confidence_text = f"{confidence:.2f}"
            values = (
                finding.tag or "—",
                _STATUS_LABELS[finding.status],
                finding.expected_value or "—",
                finding.observed_text or "—",
                confidence_text,
            )
            cells = "".join(f"<td>{escape(value)}</td>" for value in values)
            reason = (
                f'<p class="reason">{escape(finding.reason)}</p>'
                if finding.reason
                else ""
            )
            evidence = _evidence_markup(
                finding,
                image_paths,
                {image.image_id for image in inspection.images},
            )
            rows.append(
                f"<tr>{cells}</tr><tr class=\"details\"><td colspan=\"5\">"
                f"<strong>Evidence</strong>{reason}<div class=\"evidence-list\">"
                f"{evidence}</div></td></tr>"
            )
        findings_markup = (
            "<table><thead><tr><th>Tag</th><th>Status</th><th>Expected</th>"
            "<th>Read</th><th>OCR</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )
    else:
        findings_markup = '<p class="muted">No findings were recorded.</p>'

    quality_markup = (
        "".join(image_sections)
        if image_sections
        else '<p class="muted">No inspection images were recorded.</p>'
    )
    # Every dynamic string is escaped. Remaining markup and styles are fixed;
    # there is no script or user-controlled URL attribute.
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Inspection {escape(inspection.inspection_id)}</title>
<style>
body{{font:15px/1.5 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#17231d}}
h1,h2,h3{{line-height:1.2}} .meta,.photo{{border:1px solid #ccd7d0;border-radius:8px;padding:1rem;margin:1rem 0}}
table{{width:100%;border-collapse:collapse}} th,td{{padding:.65rem;text-align:left;border-bottom:1px solid #ccd7d0}}
.details td{{background:#f6f8f6}} .evidence-list{{display:flex;gap:1rem;flex-wrap:wrap}}
.evidence{{margin:.5rem 0}} .evidence img{{display:block;max-width:220px;max-height:180px;border:1px solid #9aa99f}}
.muted{{color:#59665e}} .reason{{white-space:pre-wrap}} footer{{margin-top:3rem;border-top:1px solid #ccd7d0;padding-top:1rem}}
</style></head><body>
<header><h1>Inspection report</h1><section class="meta">
<p><strong>Inspection:</strong> {escape(inspection.inspection_id)}</p>
<p><strong>Cabinet:</strong> {escape(inspection.cabinet_id)}</p>
<p><strong>Design revision:</strong> {escape(inspection.design_revision_id or '—')}</p>
<p><strong>Date:</strong> {escape(created_text)}</p>
<p><strong>Overall status:</strong> {escape(status.replace('_', ' ').title())}</p>
</section></header>
<main><h2>Photo quality</h2>{quality_markup}<h2>Findings</h2>{findings_markup}</main>
<footer>Inspection assistance only. Uncertain findings require qualified human review.</footer>
</body></html>"""


def generate_html_report(
    inspection: InspectionResult,
    image_paths: Mapping[str, str | Path],
    output_path: str | Path,
) -> Path:
    """Write one report file without overwriting an existing path."""
    destination = Path(output_path)
    html = render_html_report(inspection, image_paths)
    with destination.open("x", encoding="utf-8", newline="\n") as report_file:
        report_file.write(html)
    return destination
