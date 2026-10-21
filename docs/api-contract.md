# Initial API contract (proposal)

Keep the contract small and version it as implementation evolves. IDs below are illustrative.

## `GET /health`

Returns service status and app version.

## Planned endpoints

- `POST /api/cabinets` — create a cabinet record.
- `GET /api/cabinets/{cabinet_id}` — retrieve cabinet and design-revision summary.
- `POST /api/cabinets/{cabinet_id}/design-revisions` — register the approved reference and specification.
- `POST /api/cabinets/{cabinet_id}/inspections` — create an inspection with one or more images.
- `GET /api/inspections/{inspection_id}` — retrieve findings, evidence references and review state.
- `POST /api/findings/{finding_id}/review` — store a reviewer decision with notes.
- `POST /api/inspections/{inspection_id}/reinspection` — create a linked new inspection.
- `GET /api/cabinets/{cabinet_id}/quality-passport` — retrieve inspection history.

## Example finding object

```json
{
  "finding_id": "F-001",
  "type": "rating_mismatch",
  "expected_value": "10 A",
  "observed_text": "16 A",
  "detector_confidence": null,
  "ocr_confidence": null,
  "status": "needs_review",
  "evidence_image_id": "IMG-004",
  "design_revision_id": "REV-B"
}
```

Keep detector and OCR confidence separate. A readable OCR result is not the same as an approved engineering determination. The example is illustrative, not a real inspection result.

## Status recommendations

- `potential_mismatch`
- `needs_review`
- `inconclusive`
- `confirmed_by_reviewer`
- `rejected_by_reviewer`
- `resolved_after_reinspection`

Preserve original results and review events rather than overwriting the history.
