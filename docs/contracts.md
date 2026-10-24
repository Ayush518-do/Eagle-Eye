# Hand-over contracts

These formats let the four parts work in parallel. Change them only with agreement from both sides,
and bump `contract_version` when you do.

`contract_version: 0.1`

Coordinates are always pixels in the **original uploaded image**, as `[x_min, y_min, x_max, y_max]`,
origin at the top-left. Confidences are numbers from 0 to 1, or `null` when the step gives none.

---

## A. Drawing → backend (Part 2 produces, Part 3 consumes)

The drawing parser turns the drawing PDF into a list of **expected items**: what should be in the cabinet.

```json
{
  "contract_version": "0.1",
  "drawing_file_sha256": "…",
  "parser_version": "drawing-parser 0.1.0",
  "items": [
    {
      "tag": "CB11",
      "part_number": "…",
      "description": "Miniature circuit breaker",
      "quantity": 1,
      "rating": { "value": "10 A", "source": "schematic", "page": 5, "needs_review": false },
      "source_page": 3
    },
    {
      "tag": "PS11",
      "part_number": "…",
      "description": "Power supply",
      "quantity": 1,
      "rating": { "value": null, "source": "schematic", "page": 4, "needs_review": true },
      "source_page": 3
    }
  ]
}
```

- `needs_review: true` means the parser could not read the value reliably. Never guess a value.
- `tag` is the label printed on the cabinet part (for example `CB11`). It is the main matching key.

## B. Photo → backend (Parts 1 and 2 produce, Part 3 consumes)

Every model output on a photo is an **observation**. Detector boxes and OCR text readings use the same shape.

```json
{
  "contract_version": "0.1",
  "image_id": "IMG-001",
  "image_sha256": "…",
  "image_size": [4096, 3072],
  "observations": [
    {
      "observation_id": "OBS-001",
      "source": "detector",
      "kind": "component",
      "class_name": "mcb",
      "bbox": [1200, 830, 1290, 1105],
      "confidence": 0.81,
      "text": null,
      "text_confidence": null,
      "model": { "name": "d-fine-s", "version": "baseline-coco", "weights_sha256": "…" }
    },
    {
      "observation_id": "OBS-002",
      "source": "ocr",
      "kind": "tag_label",
      "class_name": "tag_label",
      "bbox": [1210, 790, 1280, 822],
      "confidence": 0.93,
      "text": "CB11",
      "raw_text": "C811",
      "text_confidence": 0.97,
      "model": { "name": "rapidocr", "version": "…", "weights_sha256": null }
    }
  ]
}
```

- `source` is one of `detector`, `ocr`, `manual` (drawn by a person) or `synthetic` (test data only).
- `raw_text` is exactly what OCR read; `text` is the tag it was matched to. Keep both so corrections are visible.
- `confidence` is how sure the step is that something is there; `text_confidence` is how sure the
  reader is of the characters. Keep them separate.
- An empty `observations` list is a valid answer. It means "nothing found", not "missing".

Both A and B are produced through a Python function so the backend does not depend on how the model works:

```python
# ml/interfaces.py (Part 1 and Part 2 implement; Part 3 calls)
def parse_drawing(pdf_path: str) -> dict: ...          # returns contract A
def detect_components(image_path: str) -> dict: ...    # returns contract B, kind="component"
def read_tags(image_path: str) -> dict: ...            # returns contract B, kind="tag_label"
```

If a model is not available the function raises `ModelUnavailableError` with a plain message. It never
returns made-up observations.

## C. Backend → frontend (Part 3 produces, Part 4 consumes)

Builds on [`api-contract.md`](api-contract.md). The inspection response:

```json
{
  "inspection_id": "INS-001",
  "cabinet_id": "CAB-001",
  "design_revision_id": "REV-A",
  "created_at": "2026-10-24T10:00:00Z",
  "overall_status": "review_required",
  "images": [
    { "image_id": "IMG-001", "url": "/api/images/IMG-001", "width": 4096, "height": 3072,
      "quality_flags": ["low_sharpness"] }
  ],
  "findings": [
    {
      "finding_id": "F-001",
      "type": "rating_mismatch",
      "tag": "CB11",
      "expected_value": "10 A",
      "observed_text": "16 A",
      "detector_confidence": 0.81,
      "ocr_confidence": 0.97,
      "status": "needs_review",
      "evidence": [ { "image_id": "IMG-001", "bbox": [1200, 830, 1290, 1105] } ]
    }
  ],
  "counts": { "verified": 10, "potential_mismatch": 1, "needs_review": 3, "inconclusive": 2 }
}
```

- `type`: `missing`, `unexpected`, `rating_mismatch`, `misplaced`, `verified`.
- `status`: `verified`, `potential_mismatch`, `needs_review`, `inconclusive`, `confirmed_by_reviewer`,
  `rejected_by_reviewer`, `resolved_after_reinspection`.
- `overall_status`: `pass` (all verified), `mismatch_detected` (any potential mismatch),
  otherwise `review_required`.
- The frontend draws `evidence[].bbox` on the image scaled from the original `width`/`height`.

Reviewer decision (frontend → backend): `POST /api/findings/{finding_id}/review`

```json
{ "decision": "confirmed_by_reviewer", "reviewer": "Archita", "note": "Label clearly shows 16 A" }
```

Review decisions are added as new events; the original finding is never overwritten.
