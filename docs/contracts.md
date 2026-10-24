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

**Storing expected items (backend, `POST /api/design-revisions/{id}/expected-items`).** The backend
accepts the JSON above unchanged. A list typed by hand may also leave out `parser_version`
(and `drawing_file_sha256`); `items` has the same shape. Rules:

- `contract_version` may be left out and then means `0.1`; any other value is rejected with 400.
- `drawing_file_sha256`, when given, must equal the SHA-256 of the drawing PDF stored for that
  design revision (409 if it differs or the revision has no stored hash).
- `parser_version`, when given, is stored on the design revision (400 if blank). When it is left
  out, the previously stored value is kept.
- Tags must be unique within one submission, ignoring surrounding spaces and letter case
  (`CB11` and ` cb11 ` are the same tag). A repeat is rejected with 400 and the repeated tags are
  named. For several identical parts use one item with `quantity`.
- A tag must not be blank (400). Surrounding spaces are removed before the tag is stored; letter
  case is kept (`" cb11 "` is stored as `cb11`).
- A submission replaces the whole expected-items list of that revision; it is never appended.
  It is all or nothing: if anything fails, the previous list is kept.

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

Additions made by the backend (the fields above are unchanged):

- `design_revision_id` is the revision's display label (`REV-A`), as in the example. The backend also
  returns `design_revision_internal_id`, the id used in URLs and in the create-inspection form.
- `GET /api/inspections/{id}` also returns `state` (`queued`, `running`, `done`, `failed`) and, when
  failed, `error`. `overall_status` is `null` until `state` is `done`.
- `status` and `overall_status` are the current values: the latest reviewer decision on a finding
  replaces its original status in the response (the original is kept in the database).
- `quality_flags` contains `quality_not_measured` while no image-quality check has run, so an empty
  list is never read as "no problems".

Reviewer decision (frontend → backend): `POST /api/findings/{finding_id}/review`

```json
{ "decision": "confirmed_by_reviewer", "reviewer": "Archita", "note": "Label clearly shows 16 A" }
```

Review decisions are added as new events; the original finding is never overwritten.

---

## D. Backend endpoints around the contracts (implemented; shapes proposed, not yet agreed)

`docs/team/backend.md` names these endpoints but gives no bodies or responses for most of them. The
shapes below are what the backend implements today, taken from the examples above and the field
names `frontend/src/api.js` reads. They are proposals until Parts 3 and 4 agree on them.

Every error body is `{"detail": "plain message"}` (400 bad input, 404 not found, 409 conflict, 422
malformed request, 500 unexpected).

| # | Endpoint | Request | Success response |
|---|---|---|---|
| 1 | `POST /api/cabinets` | JSON `cabinet_id` (letters, digits, `.` `_` `-`, up to 40), `name` | 201 `{cabinet_id, name, created_at}`; 409 if the id exists |
| 2 | `GET /api/cabinets` | | list of `{cabinet_id, name, created_at, latest_inspection_id, latest_inspection_state, latest_overall_status}`; the last three are `null` before any inspection or until a run is done |
| 3 | `GET /api/cabinets/{id}` | | `{cabinet_id, name, created_at, design_revisions: [{design_revision_id, cabinet_id, label, drawing_sha256, parser_version, created_at}]}` |
| 4 | `POST /api/cabinets/{id}/design-revisions` | form `label`, `drawing` (a complete PDF) | 201 design revision as above; `design_revision_id` here is the internal id |
| 5 | `POST /api/design-revisions/{id}/expected-items` | Contract A (see above) | 201 the stored items in the Contract A shape (`parser_version` may be `null`) |
| 5b | `GET /api/design-revisions/{id}/expected-items` | | same shape |
| 6 | `POST /api/cabinets/{id}/inspections` | form `design_revision_id` (the internal id), `photos` (1 to 10 JPEG or PNG) | 202 `{inspection_id, state: "queued"}` |
| 7 | `POST /api/inspections/{id}/observations` | Contract B for one stored image (`image_id` is the id from the inspection); `source` must be `manual`; boxes must lie inside the image | 201 the stored observations of that image, Contract B |
| 7b | `GET /api/inspections/{id}/observations` | | list of Contract B blocks, one per image |
| 8 | `POST /api/inspections/{id}/run` | | 202 `{inspection_id, state: "running"}`; 409 unless the state is `queued` or `failed` |
| 9 | `GET /api/inspections/{id}` | | Contract C plus `state`, `error`, `design_revision_internal_id` |
| 10 | `GET /api/images/{image_id}` | | the stored photo |
| 11 | `POST /api/findings/{id}/review` | `{decision, reviewer, note}`; `decision` is `confirmed_by_reviewer` or `rejected_by_reviewer` | 201 `{finding_id, decision, reviewer, note, created_at}` |
| 12 | `POST /api/inspections/{id}/reinspection` | form `photos` (1 to 10 JPEG or PNG) | 202 `{inspection_id, state: "queued", previous_inspection_id}`; 404 unknown inspection; 409 unless the earlier inspection is `done`, or if another reinspection of it is still `queued` or `running` |
| 13 | `GET /api/cabinets/{id}/quality-passport` | | `{cabinet_id, name, inspections: [...]}`, oldest first, `[]` when there are none. Each entry: `inspection_id, state, error, created_at, design_revision_id` (label), `design_revision_internal_id, previous_inspection_id, overall_status` (current; `null` unless `done`), `engine_overall_status` (as stored when the run finished), `images: [{image_id, sha256, width, height, quality_flags}]`, `findings: [{finding_id, type, tag, original_status, current_status, reason}]`, `review_events: [{finding_id, decision, reviewer, note, created_at}]` |

Reinspection: a new inspection of the same cabinet and design revision, linked through
`previous_inspection_id` (also returned by `GET /api/inspections/{id}`). It is not rewritten into
the earlier one: the earlier inspection, its findings and its review events stay as they were. The
new inspection is queued; give it observations and run it like any other. **Nothing is marked
`resolved_after_reinspection` automatically**; how a reinspection resolves earlier findings is not
decided yet.

Quality passport: stored data only, using the same status derivation as `GET /api/inspections/{id}`.
It records what was inspected and decided; it does not state that a cabinet is compliant, approved
or safe.

Validation notes: a PNG is checked completely (checksums and pixel stream); a JPEG is checked
marker by marker and then fully decoded with Pillow, and its decoded format and size must match;
photos may not exceed about 89 million pixels; a PDF is checked for a header, a trailer and a valid
cross-reference pointer. A decodable JPEG can still hold damaged pixel data, because the decoder
hides errors inside a complete scan. None of this proves a file is a good photo or a real
drawing.
