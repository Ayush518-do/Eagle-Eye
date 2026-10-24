# Hand-over contracts

These are the agreed data formats between the parts of Eagle Eye. Each team codes against this file,
not against another team's code, which is what lets everyone work at the same time.

`contract_version: 0.3`

Change this file only with agreement from both sides of a hand-over, and bump the version when you do.
**0.2 adds:** arrangement (group + position) and `component_type` on expected items; finding types
`order_changed` and `type_mismatch`; evidence sources and score on findings; the arrangement summary;
the analytics response.
**0.3 adds:** ghost overlay: drawing layout position per expected item, photo alignment points,
`expected_bbox` on findings and ghost boxes per photo (section E).

**Rules for every format:**

- Coordinates are pixels in the **original uploaded photo**, `[x_min, y_min, x_max, y_max]`, with the
  origin at the top-left.
- Confidences are numbers from 0 to 1, or `null` when a step gives none.
- New fields are optional unless marked *required*, so older data still loads.

---

## A. Drawing → backend: expected items

Produced by the drawing parser (ML) or typed in by hand in the parts editor (frontend).

```json
{
  "contract_version": "0.2",
  "drawing_file_sha256": "…",
  "parser_version": "drawing-parser 0.1.0",
  "items": [
    {
      "tag": "CB13",
      "component_type": "mcb",
      "part_number": "A9N2P16CIN",
      "description": "Miniature circuit breaker 2P",
      "quantity": 1,
      "rating": { "value": "16 A", "source": "schematic", "page": 9, "needs_review": false },
      "arrangement": { "group": "left_breaker_rail", "position": 3, "direction": "top_to_bottom" },
      "layout": { "page": 5, "view": "left_inside", "bbox": [97.9, 294.4, 115.2, 301.3], "anchor": "callout" },
      "source_page": 5
    },
    {
      "tag": "PS11",
      "component_type": "power_supply",
      "description": "Power supply 24 V DC",
      "quantity": 1,
      "rating": { "value": null, "source": "schematic", "page": 10, "needs_review": true },
      "arrangement": { "group": "power_row_lower", "position": 1, "direction": "left_to_right" },
      "source_page": 5
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `tag` *(required)* | The label printed on the part, e.g. `CB13`. The main matching key |
| `component_type` | One of `mcb`, `isolator`, `power_supply`, `redundancy_module`, `io_module`, `controller`, `terminal_block`, `other`. Used for the type check |
| `rating.needs_review` | `true` = the value couldn't be read reliably. Never guess a value |
| `arrangement.group` | Name of a row or rail of parts that sit in a line, e.g. `left_breaker_rail` |
| `arrangement.position` | 1 = first in that group, counted in `direction` |
| `arrangement.direction` | `top_to_bottom` or `left_to_right` |
| `layout` | Where the tag sits on the drawing's general-arrangement page: `page`, `view` (e.g. `front_inside`), `bbox` in **PDF points** (the drawing's own coordinates). `anchor` = `component` (tiny tag text drawn on the part itself) or `callout` (label beside the drawing, same height as the part but off to the side). Used for the ghost overlay |

`component_type` from the tag prefix, when the drawing doesn't say otherwise:

| Prefix | Type |
|---|---|
| `CB` | `mcb` |
| `DS` | `isolator` (DS1–DS3) or `mcb` (DS11–DS22): check the drawing |
| `PS` | `power_supply` |
| `D` + digits | `redundancy_module` |
| `X…` | `terminal_block` |

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

## B. Photo → backend: observations

Everything a model (or a person) sees in a photo is an **observation**.

```json
{
  "contract_version": "0.2",
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
      "raw_text": null,
      "text_confidence": null,
      "model": { "name": "rf-detr-small", "version": "eagle-v1", "weights_sha256": "…" }
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

- `source`: `detector` (trained), `zero_shot` (pretrained, from a text prompt), `ocr`, `manual`
  (drawn by a person), or `synthetic` (tests only, never in a real result).
- `kind`: `component` (a box around a part), `tag_label` (a box around a printed tag), or
  `rating_text` (a box around rating text such as "16A").
- `raw_text` is exactly what was read. `text` is the tag it was matched to. Keep both.
- `confidence` = how sure that something is there. `text_confidence` = how sure of the characters.
- An empty list is valid. It means "nothing found", **not** "missing".

Python entry points (ML implements, backend calls):

```python
# ml/interfaces.py
def parse_drawing(pdf_path: str) -> dict: ...          # contract A
def detect_components(image_path: str) -> dict: ...    # contract B, kind="component"
def read_tags(image_path: str) -> dict: ...            # contract B, kind="tag_label" / "rating_text"
```

A model that isn't available raises `ModelUnavailableError` with a plain message. It never returns
made-up observations.

## C. Backend → frontend: inspection result

`GET /api/inspections/{id}`

```json
{
  "inspection_id": "INS-001",
  "cabinet_id": "CAB-001",
  "design_revision_id": "REV-A",
  "previous_inspection_id": null,
  "state": "done",
  "error": null,
  "created_at": "2026-10-24T10:00:00Z",
  "overall_status": "review_required",
  "images": [
    { "image_id": "IMG-001", "url": "/api/images/IMG-001", "width": 4096, "height": 3072,
      "quality_flags": ["low_sharpness"], "alignment_set": true,
      "ghost": [ { "tag": "CB14", "bbox": [1500, 1100, 2000, 1220], "status": "inconclusive" } ] }
  ],
  "findings": [
    {
      "finding_id": "F-001",
      "type": "rating_mismatch",
      "tag": "CB11",
      "component_type": "mcb",
      "expected_value": "10 A",
      "observed_text": "16 A",
      "detector_confidence": 0.81,
      "ocr_confidence": 0.97,
      "sources": ["ocr", "detector"],
      "evidence_score": 0.88,
      "status": "potential_mismatch",
      "reason": "Rating on the breaker differs from the drawing.",
      "evidence": [ { "image_id": "IMG-001", "bbox": [1200, 830, 1290, 1105] } ],
      "expected_bbox": null,
      "reviews": []
    }
  ],
  "arrangement": [
    {
      "group": "left_breaker_rail",
      "direction": "top_to_bottom",
      "expected_order": ["CB11", "CB12", "CB13", "CB14", "CB15", "CB16"],
      "observed_order": ["CB11", "CB12", "CB14", "CB13", "CB15", "CB16"],
      "out_of_order": ["CB13"],
      "status": "order_changed"
    }
  ],
  "counts": { "verified": 10, "potential_mismatch": 1, "needs_review": 3, "inconclusive": 2 }
}
```

**Finding `type`:**

| Type | Meaning |
|---|---|
| `verified` | Expected part found and matches |
| `missing` | Expected part not found. Status is `inconclusive` unless its area is clearly visible |
| `unexpected` | Found but not in the drawing |
| `rating_mismatch` | Rating read differs from the drawing |
| `type_mismatch` | The tag says one kind of part (e.g. PS11 = power supply) but a different kind is under it |
| `order_changed` | Part is in a different position in its group than the drawing says |
| `misplaced` | Part is in a different group or area (later) |

**Finding `status`:** `verified`, `potential_mismatch`, `needs_review`, `inconclusive`,
`confirmed_by_reviewer`, `rejected_by_reviewer`, `resolved_after_reinspection`.

**Arrangement `status`:** `matches`, `order_changed` (review required, **not** a defect by itself),
`not_enough_evidence` (fewer than 2 tags of the group were read).

**`overall_status`:** `pass` (every finding verified or confirmed fine), `mismatch_detected` (any
`potential_mismatch`), otherwise `review_required`. An order change alone gives `review_required`.

**`sources` / `evidence_score`:** which kinds of evidence agree on this finding, and a 0–1 summary.
For example, OCR + trained detector + zero-shot detector all agreeing gives a high score; OCR alone gives a lower one.

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

Reviews are added as new events. The original finding is never overwritten. `reviews[]` lists them, oldest first.

## D. Backend → frontend: analytics

`GET /api/analytics?from=2026-10-01&to=2026-10-31`

```json
{
  "inspections": 12,
  "overall": { "pass": 5, "review_required": 6, "mismatch_detected": 1 },
  "findings_by_type": { "missing": 4, "unexpected": 1, "rating_mismatch": 2, "order_changed": 3, "type_mismatch": 0 },
  "top_flagged_tags": [ { "tag": "CB14", "count": 3 }, { "tag": "PS11", "count": 2 } ],
  "review_outcomes": { "confirmed_by_reviewer": 4, "rejected_by_reviewer": 2, "pending": 5 },
  "per_day": [ { "date": "2026-10-24", "inspections": 3, "mismatch_detected": 1 } ]
}
```

## E. Ghost overlay: alignment and expected positions

The ghost overlay lays the drawing, faded, over a photo and shows where each expected part *should* be.
The drawing and the photo don't line up by themselves, so a person clicks the **same 4 corners** (for
example, the corners of the mounting plate) once on the drawing page and once on the photo.

Save alignment: `PUT /api/images/{image_id}/alignment`

```json
{
  "drawing_page": 5,
  "drawing_points": [[394, 177], [580, 177], [580, 637], [394, 637]],
  "photo_points":   [[640, 980], [3520, 1010], [3490, 2950], [610, 2920]]
}
```

- `drawing_points` are in PDF points on that page; `photo_points` are in original-photo pixels.
- Points go in the same order on both: top-left, top-right, bottom-right, bottom-left.
- `GET` on the same path returns it; `DELETE` removes it.

Drawing page image: `GET /api/design-revisions/{id}/drawing-pages/{page}.png?width=2000` returns the
page rendered as a picture, plus the header `X-Page-Size: 1191x842` (page size in PDF points), so the
frontend can convert clicks on the picture into PDF points.

With an alignment saved, the inspection result (section C) includes per image:

- `alignment_set: true`
- `ghost[]`: one box per expected item whose `layout` is on that drawing page, mapped into photo
  pixels, with its finding status.
- Findings of type `missing` get `expected_bbox`: the approximate spot on the photo where the part
  should be.

**Ghost boxes are approximate hints.** The drawing isn't drawn exactly to scale and the photo is taken
at an angle, so they never decide a finding on their own. They only show the reviewer where to look.

---

## F. Backend endpoints around the contracts (implemented; shapes proposed, not yet agreed)

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
