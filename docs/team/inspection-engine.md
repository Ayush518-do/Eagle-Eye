# Task 3: Inspection engine (rules, photo quality, reports): complete guide

**Branch:** `feature/inspection-engine`
**You own:** `backend/app/pipeline/`, `backend/app/reports/`, `backend/tests/test_engine_*.py`,
`backend/tests/test_compare.py`, `config/thresholds.yaml`.
**Don't edit:** API routes or database code (Task 1), `frontend/` (Task 2), `ml/`.
You may add packages to `backend/requirements.txt`; tell Task 1, who shares that file.

This file covers your work **until the project is finished**. Work through the milestones in order.
If something is unclear or blocked, tell the team lead; don't guess.

---

## 0. What you're building

The engine is the "brain". It takes *what the drawing expects* and *what was seen in the photos*, and
produces findings. It's **plain Python**: no web code, no database. That makes every rule easy to test
with small hand-written examples.

```text
expected items (contract A) ─┐
observations   (contract B) ─┼─► run_inspection() ─► findings + arrangement + photo flags + overall status
photo files                 ─┘
```

Observations come from several **sources**: `manual` boxes now, then `ocr`, `detector` and `zero_shot`
when ML is ready. The engine treats them all the same way, so **nothing changes when ML arrives**.

All data shapes are in **`docs/contracts.md` (version 0.2)**. `backend/app/schemas.py` (Task 1) holds the
Python versions; import from there.

## 1. What already exists

`backend/app/pipeline/compare.py` (tests in `backend/tests/test_compare.py`):

- tag read with high confidence → `verified`; low confidence → `needs_review`
- not read anywhere → `missing` with status `inconclusive`
- read but not in the drawing → `unexpected`, `needs_review`
- refuses `source: "synthetic"` data in a real run

Keep these tests passing throughout.

## 2. Rules that never change

1. **The engine only ever lowers certainty** (e.g. `verified` → `needs_review`), never raises it.
2. **Not seen ≠ missing.** "Missing" needs clear evidence (rule in M2.3); otherwise `inconclusive`.
3. **Never guess** a rating, tag or order you can't read. Leave it out and say why in `reason`.
4. **Every number** (threshold, distance) lives in `config/thresholds.yaml`, never in the code.
5. **Every rule has a test**, with the input and expected output written out in the test.

---

## Milestone 1: Core engine (must have, do first)

### 1.1 The single entry point
`backend/app/pipeline/engine.py`. Task 1 calls **only this**, so keep its name and arguments stable:

```python
@dataclass
class EngineResult:
    findings: list[Finding]
    arrangement: list[ArrangementResult]
    image_flags: dict[str, list[str]]     # {"IMG-001": ["low_sharpness"]}
    overall_status: str                   # pass | review_required | mismatch_detected
    counts: dict[str, int]

def run_inspection(expected_items, observations_by_image, image_paths, thresholds=None) -> EngineResult:
    t = thresholds or load_thresholds()
    image_flags = {img: check_photo(path, t) for img, path in image_paths.items()}
    merged = fuse_observations(observations_by_image, t)          # M3.1; returns input unchanged at first
    findings = compare(expected_items, merged, t)                  # presence + unexpected
    findings += check_ratings(expected_items, merged, t)           # M1.4
    findings += check_types(expected_items, merged, t)             # M3.2
    arrangement = check_arrangement(expected_items, merged, t)     # M2.1
    findings = apply_confidence_gate(findings, image_flags, t)     # M1.3
    return EngineResult(findings, arrangement, image_flags,
                        overall_status(findings), count_by_status(findings))
```

Build it with simple versions first (functions that return empty lists), so Task 1 can call it on day 1.

### 1.2 Thresholds file
`config/thresholds.yaml` and a `load_thresholds()` loader:

```yaml
min_text_confidence: 0.80        # below this an OCR reading needs review
min_detector_confidence: 0.50
min_photo_width: 1600            # pixels
min_sharpness: 100.0             # variance of the Laplacian, see 1.3
max_overexposed_fraction: 0.15
label_to_component_max_gap: 0.6  # in label heights, for M3.1
iou_agree: 0.5                   # box overlap needed for two detectors to "agree"
rating_search_margin: 0.2        # widen a component box by 20 % when looking for its rating text
```

These are starting guesses. Write down which ones you tuned, and on what photos.

### 1.3 Photo-quality checks + confidence gate
`backend/app/pipeline/image_quality.py` (`pip install opencv-python-headless`):

| Flag | How to measure | Meaning |
|---|---|---|
| `low_resolution` | width < `min_photo_width` | labels may be too small to read |
| `low_sharpness` | variance of the Laplacian < `min_sharpness` | probably blurry |
| `overexposed` | share of pixels with brightness > 250 is above the limit | glare may hide labels |

*Variance of the Laplacian* in plain words: the Laplacian highlights edges. A sharp photo has strong
edges, so the variance is high; a blurry photo has weak edges, so it's low.

```python
gray = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
```

`apply_confidence_gate()`:

| Situation | Result |
|---|---|
| `verified`, but every photo showing it is `low_sharpness` | → `needs_review`, reason "photo may be blurry" |
| `potential_mismatch` read below `min_text_confidence` | → `needs_review` |
| expected item has `rating.needs_review: true` | rating check skipped, reason says so |
| two photos read different text in the same tag area | → `needs_review`, both readings in `reason` |

**Test:** a sharp generated image, and a blurred copy (`cv2.GaussianBlur`) that must get `low_sharpness`.

### 1.4 Rating check
`backend/app/pipeline/ratings.py`:

```python
normalise_rating("10 A")  -> ("A", 10.0)
normalise_rating("10A")   -> ("A", 10.0)
normalise_rating("C10")   -> ("A", 10.0)    # breaker marking: curve C, 10 amps
normalise_rating("16A")   -> ("A", 16.0)
normalise_rating("40A Power Supply") -> ("A", 40.0)
normalise_rating("24VDC") -> ("V", 24.0)
normalise_rating("CB11")  -> None           # a tag, not a rating
```

- Find rating text **inside or next to** the part's box: the component box widened by `rating_search_margin`.
- Same unit and value: nothing extra. Different value: `rating_mismatch` / `potential_mismatch`, with
  `expected_value` and `observed_text`. Can't parse: leave it alone, never guess.

**Check:** `pytest backend/tests -q` passes. Task 1 can call `run_inspection()` and gets real findings
from manual boxes.

---

## Milestone 2: Selected features (high priority)

### 2.1 Arrangement / order check (new feature)
`backend/app/pipeline/arrangement.py`. For each `arrangement.group` in the expected items:

1. **Expected order:** the group's tags sorted by `position`.
2. **Observed order:** the tags read in the photo, sorted by box centre: `y` for `top_to_bottom`, `x` for
   `left_to_right`. Use one photo per group (the one with the most tags read in that group).
3. **Compare with the longest common subsequence (LCS).** An LCS is the longest list of tags that
   appear in the same order in both lists, though not necessarily side by side. Tags outside it are out
   of order.

```text
expected: CB11 CB12 CB13 CB14 CB15 CB16
observed: CB11 CB12 CB14 CB13 CB15 CB16
LCS:      CB11 CB12 CB14      CB15 CB16   (CB11 CB12 CB13 CB15 CB16 is equally long)
out_of_order: ["CB13"]  → status "order_changed", one finding type "order_changed", status needs_review

For a swap, either tag can be the one left out; the code below picks CB13. Both are correct.
The frontend highlights both swapped tags, so it doesn't matter for the user.
```

```python
def lcs(a, b):
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) - 1, -1, -1):
        for j in range(len(b) - 1, -1, -1):
            dp[i][j] = dp[i+1][j+1] + 1 if a[i] == b[j] else max(dp[i+1][j], dp[i][j+1])
    out, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]: out.append(a[i]); i += 1; j += 1
        elif dp[i+1][j] >= dp[i][j+1]: i += 1
        else: j += 1
    return out
```

Rules:
- Compare only tags that were **both expected and read** in that group. Missing tags are reported by
  the presence check, not here.
- Fewer than 2 such tags → `not_enough_evidence`.
- Order change → status `needs_review`, **never** `potential_mismatch`. An order change is not a defect by itself; the reviewer decides.
- Ties (two tags with nearly the same centre, within half a label height) → `not_enough_evidence`, with reason.

Tests: matching order; one swap; a tag moved to the end; 1 tag read; ties; a horizontal group.

### 2.2 Multiple photos
Combine evidence across photos **by tag**:

- **Present** if any clear photo reads it.
- **Different readings** in different photos → `needs_review`, both listed.
- `evidence[]` lists every photo where it was seen.

### 2.3 "Missing" needs clear evidence
An expected tag that wasn't read is `missing` + `inconclusive` **unless** all of these hold:

- the photo covering its group has no quality flags,
- at least 2 other tags of the same group were read (so the group is clearly in view),
- its expected position falls between them and nothing was read there.

Only then does it become `missing` + `potential_mismatch`, with reason "group visible, CB14 not found
between CB13 and CB15".

### 2.4 Reinspection comparison
`compare_with_previous(old_findings, new_findings)`: an old finding becomes
`resolved_after_reinspection` **only** if the new inspection has that tag `verified`. Everything else
stays open. Old findings are never deleted.

### 2.5 Report and CSV
`backend/app/reports/html_report.py` with Jinja2 (`pip install jinja2`):
`render_report(inspection: InspectionResult, image_paths) -> str` (HTML). Include:

- cabinet, revision, date, overall status, counts
- findings table (same columns as the frontend), arrangement cards
- a small cropped picture of each finding's evidence box (Pillow `Image.crop`, embedded as base64)
- photo-quality flags in plain words
- review decisions so far
- footer: "Inspection assistance only. Uncertain findings require qualified human review."

`backend/app/reports/export.py`: `findings_to_csv(inspection) -> str` with columns
`finding_id,tag,type,status,expected,observed,ocr_confidence,sources,reason,last_review`.

---

## Milestone 3: Fusion and extras

### 3.1 Evidence fusion (prepares for ML; build now with manual boxes)
`backend/app/pipeline/fusion.py`, `fuse_observations(...)`:

1. **Detectors agree:** a `detector` box and a `zero_shot` box with the same class and IoU ≥ `iou_agree`
   become one component with both sources. *IoU* (intersection over union) = overlap area ÷ combined
   area: 1 is identical, 0 is no overlap.
2. **Attach tags to components:** a `tag_label` belongs to the component box it sits inside, or directly
   above or below, within `label_to_component_max_gap` label heights. That gives the component its tag.
3. **Evidence score per finding:**
   ```text
   ocr tag read                       +0.5 × text_confidence
   trained detector box agrees        +0.3 × confidence
   zero-shot box agrees               +0.2 × confidence
   manual box                         = 1.0 (a person drew it)
   ```
   Store `sources` (e.g. `["ocr","detector"]`) and `evidence_score` on each finding.

Tests with hand-made boxes: two overlapping boxes merge; far-apart boxes don't; a label above a box
attaches; a label far away doesn't.

### 3.2 Type check
`check_types(...)`: if the expected `component_type` of a tag (e.g. PS11 → `power_supply`) differs from
the class of the component box it's attached to (e.g. `mcb`), give a `type_mismatch` with status
`needs_review`. This only runs when a component box exists; otherwise skip it.

### 3.3 Analytics summary
`backend/app/pipeline/analytics.py`: `summarise(inspections) -> dict` in the shape of contract D.
Task 1 calls it with stored inspections.

### 3.4 QR on the report
Add the cabinet's QR code (`pip install qrcode[pil]`) to the report header, linking to
`{FRONTEND_URL}/cabinets/{id}`.

---

### 3.5 Ghost overlay projection (contract section E)
`backend/app/pipeline/ghost.py`. With 4 matching corner points on the drawing and on the photo,
OpenCV computes a **homography**: a transform that maps any point on one flat surface to the same
point on the other, even when the photo is taken at an angle.

```python
import numpy as np, cv2

def project_boxes(drawing_points, photo_points, boxes):
    """Map boxes from drawing coordinates (PDF points) to photo pixels."""
    M = cv2.getPerspectiveTransform(np.float32(drawing_points), np.float32(photo_points))
    out = []
    for x1, y1, x2, y2 in boxes:
        corners = np.float32([[x1, y1], [x2, y1], [x2, y2], [x1, y2]]).reshape(-1, 1, 2)
        p = cv2.perspectiveTransform(corners, M).reshape(-1, 2)
        out.append([float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max())])
    return out

# Example: drawing panel 100..300 × 200..600 points, photo panel 1000..3000 × 500..2900 pixels
# project_boxes(d, p, [[150, 300, 200, 320]])  ->  [[1500.0, 1100.0, 2000.0, 1220.0]]
```

`project_expected_positions(expected_items, alignment, image_size) -> list[{"tag", "bbox"}]`:

- Only items whose `layout.page` equals `alignment.drawing_page`.
- If `layout.anchor` is `callout`, the box sits beside the part, not on it. Use only its height (y) to
  place a row marker across the rail, and say "approximate row" in the ghost label.
- Drop boxes that land outside the photo.
- Raise `ValueError("alignment points are on one line")` if 3 of the 4 points are nearly in a straight line.
- Add `expected_bbox` to `missing` findings. **Never** change a status because of the ghost: it's a hint.

Tests: the example above; points in a different order; a box outside the photo is dropped; points on one line raise an error.

## Milestone 4: ML integration (when models are connected)

- Real `ocr`, `detector` and `zero_shot` observations flow through the same functions. Re-run every
  test, plus one end-to-end test on the demo cabinet.
- Tune `config/thresholds.yaml` on the company close-up photos. Record the before/after values and
  the photos used in `config/THRESHOLDS_NOTES.md`.
- Measure each source **alone** and **merged**, on the same hand-made answer key (a list of the correct
  tags per photo), so "merging helps" is a measured claim, not an assumption.

## Milestone 5: Demo hardening

- Run the engine on all company photos; no crash on any of them.
- Perturbation tests (clearly labelled `synthetic`): swap two tags (expect `order_changed`); remove one
  tag (expect `missing`); change a rating text (expect `rating_mismatch`).
- Time `run_inspection` on a 4096×3072 photo; keep it under a few seconds without ML.

---

## Done when

- [ ] `run_inspection()` returns `EngineResult` and Task 1 uses it.
- [ ] Photo checks, gate, ratings, arrangement, multi-photo, missing rule, reinspection, fusion, type check,
      analytics, report and CSV all exist with passing tests.
- [ ] Every threshold is in `config/thresholds.yaml`.
- [ ] The HTML report opens in a browser and prints cleanly.

## Working with the others

- **Backend (Task 1)** calls `run_inspection`, `render_report`, `findings_to_csv` and `summarise`. Tell
  them before changing any of these signatures.
- **Frontend (Task 2)** displays your statuses and arrangement results exactly as defined in
  `docs/contracts.md`. A new status or type needs a contract update first.
- Merge `develop` into your branch daily: `git pull origin develop`. Open a pull request into `develop`
  at the end of each milestone.
The ML parts produce the same observation format as manual boxes, so the engine doesn't change;
only `source` becomes `detector` or `ocr`. That's the reason for building on the contract now.

## Implementation and integration handoff (2026-10-24)

This section records the behavior currently implemented on `feature/inspection-engine`. It does
not change the requirements above or claim that unsupported component, rating, API, or persistence
behavior is complete.

### Module boundary and entry points

The inspection-engine module owns deterministic comparison, photo-quality flags, reinspection
comparison, result assembly, and report rendering. The application service owns request handling,
authorization, trusted storage paths and URLs, persistence, inspection/cabinet identifiers, and
cross-request orchestration. This module adds no API routes or database behavior.

Public engine functions:

```python
run_inspection(expected_items, observations_by_image, image_paths, thresholds=None)
    -> tuple[list[Finding], dict[str, list[str]]]

run_inspection_from_contracts(drawing_contract, image_contracts_by_id, image_paths, thresholds=None)
    -> tuple[list[Finding], dict[str, list[str]]]

run_reinspection(previous_findings, expected_items, observations_by_image, image_paths, thresholds=None)
    -> tuple[list[Finding], dict[str, list[str]]]
```

`run_inspection` accepts validated `ExpectedItem` and `Observation` objects. `run_inspection_from_contracts`
accepts contract A and a mapping of image IDs to contract B dictionaries, validates the supported
versions and producer fields, checks declared dimensions and evidence boxes against the original
images, then calls the same engine. Additional image paths without an observation contract are still
quality assessed. Synthetic observations are rejected by the comparison path. An expected tag not read in
the supplied photos is represented with finding type `missing` and status `inconclusive`; the status
must never be interpreted as proof that the physical component is absent.

At present, `compare()` matches expected tags to `tag_label` observations. It does not compare
`component` detector observations against drawing items, because contract A has no expected detector
class or component geometry and contract B has no approved tag-to-component association rule.
Position and ordering comparisons are likewise unsupported by the current contracts and are not
inferred. `min_detector_confidence` is validated from configuration but is not applied to a detector
comparison path.

### Contract v0.2 inputs

The canonical producer shapes and examples are in [`../contracts.md`](../contracts.md). The drawing
parser returns contract A (`contract_version`, `parser_version`, `items`, with optional drawing hash).
The OCR/detector producers return contract B (`contract_version`, `image_id`, original-image
`image_size`, and `observations`). Boxes are pixel coordinates `[x_min, y_min, x_max, y_max]` in
the original image. Contract adapter input must identify each image contract under its own `image_id`
and supply the matching original image path. Drawing contracts must be v0.2; image contracts may be
v0.2 or the additive v0.3 emitted by the available detector producer, provided their observation
fields validate against the current schema. Unsupported extra fields, malformed values, other version
mismatches, duplicate observation IDs within an image, mismatched dimensions, and out-of-image boxes
are rejected with validation errors.

### Detector producer compatibility review (2026-10-24)

Read-only inspection of local ref `origin/feature/ml-detection` at
`6cffc6e5b4acb998b64d6ca6f4950aee13ec7d9d` found a detector producer in
`ml/detection/detector.py`, `ml/detection/zero_shot.py`, and `ml/interfaces.py`.
`RFDETRDetector.predict()` and `OWLv2Detector.predict()` return dictionaries with
`bbox`, `score`, and `class_name`; tiling maps boxes back to original-image pixel
coordinates. `detections_to_contract()` emits `image_size` from the source image,
uses the path stem as `image_id`, maps `score` to `confidence`, and marks outputs
as `kind="component"`. RF-DETR uses source `detector`, which the engine accepts
under the current schema. OWLv2 uses source `zero_shot`, which contract v0.2's
`Observation.source` does not allow and the engine correctly rejects; supporting
it requires an agreed contract/schema update. The producer labels image contracts
v0.3; the engine accepts that version for the RF-DETR image payload only when all
fields still validate against its existing observation schema. Unknown fields
and invalid confidence, boxes, or dimensions remain rejected.

The detector source declares `mcb` as the only RF-DETR-trained class; `power_supply`
and `io_module` are OWLv2 prompt classes. `class_name` remains an open string in
the shared schema, so the engine does not invent a closed class map. The engine
does not compare component classes, positions, or ordering with expected items:
comparison consumes tag-label observations only and has no approved tag-to-component
association rule. Model confidence is passed through as the producer's score; a
detector comparison or detector confidence gate is not implemented. Rating mismatch
generation remains disabled pending approved calibration.

This verifies payload-shape compatibility with the producer code, not a live model
inference run: no detector weights or registry are present in the inspected Git ref
or current workspace. The producer derives IDs from filename stems, so duplicate
stems across directories need a service-level unique-ID mapping before combining
those image contracts.

OCR observations use `kind="tag_label"` for ordinary text/tag readings and `kind="rating"` only
when the OCR string matches one of the explicitly supported rating formats. A rating observation
uses `source="ocr"`, `class_name="rating"`, exact OCR text in `raw_text`, `text=None`, and the OCR
box. Matched expected tags take precedence over rating parsing. Unrecognized OCR text is not
classified as a rating. Tag-label and component semantics remain separate.

### Confidence, image quality, and thresholds

`config/thresholds.yaml` is the single configuration source for `min_text_confidence`,
`min_detector_confidence`, `min_photo_width`, `min_sharpness`, and
`max_overexposed_fraction`. The loader rejects missing, duplicate, unknown, non-numeric, non-finite,
and out-of-range values. Missing/unreadable images fail quality inspection rather than returning a
clean flag list. Image quality currently uses Pillow and a four-neighbor discrete Laplacian
variance; it flags width below the configured minimum, sharpness below the configured value, and
the fraction of grayscale pixels above 250 greater than the configured maximum. The committed
values are starting guesses, not values tuned on representative cabinet photos.

The confidence gate lowers a verified finding to `needs_review` when its evidence is absent from
the assessed image map or all evidence images are flagged `low_sharpness`. A `potential_mismatch`
with missing or below-threshold OCR confidence becomes `needs_review`. Conflicting tag text read
across images becomes `needs_review`. Image flags unrelated to a finding do not gate it. No rule
raises certainty, and unseen items remain `inconclusive`.

### Reinspection

`run_reinspection` runs the regular engine and passes the IDs of images assessed in that run to
`compare_with_previous`. The helper preserves prior findings and IDs where possible; it resolves a
prior issue only when a current finding is verified, has evidence, and that evidence references an
assessed current image. Ambiguous matches remain `needs_review`; duplicate IDs are repaired to keep
IDs unique within the returned list. Semantic matching uses finding type, normalized tag, expected
value, and observed text rather than list order or per-run ID. This is not a database-backed,
cross-request identity guarantee; persistence owners must retain the returned IDs and prior image
records.

### Rating helpers and calibration gate

`backend.app.pipeline.ratings.normalise_rating()` parses only `10 A`, `10A`, `C10`, and `24VDC`
into normalized unit/value pairs; `CB11`, malformed values, and unsupported forms return `None`.
The parser implementation is isolated in dependency-free `backend.app.pipeline.rating_format`, so
the OCR producer can classify explicit rating strings without importing Pydantic schemas or the
backend rating-finding implementation. The helpers can measure center-to-center distance between
rating and expected-tag boxes, normalized
by image diagonal, and compare candidates when given a caller-attested test/manual distance limit.
That attestation is not proof of calibration. `run_inspection()` does not call the rating helpers
and cannot emit production `rating_mismatch` findings at this time.

Before activation, collect reviewed annotations from representative cabinet photos: rating boxes,
tag-label boxes, image dimensions, the true tag association for each rating, and hard negatives
(nearby unrelated tags/ratings, multiple tags, repeated and conflicting readings, and OCR errors).
Split by cabinet/drawing to avoid near-duplicate leakage. Evaluate candidate distance limits on
held-out examples with association precision, false-association rate, recall, and per-condition
results; prioritize avoiding false associations. Record the dataset provenance, annotation review,
chosen limit, and evaluation output, then obtain explicit team/mentor approval before adding the
production configuration value or enabling findings. No calibration dataset or approved limit is
currently available.

### Result assembly and report

The service supplies the result metadata through:

```python
assemble_inspection_result(
    *, inspection_id, cabinet_id, created_at, findings, image_flags,
    image_paths, image_urls, design_revision_id=None, prior_images=()
) -> InspectionResult
```

The service must pass trusted local original-image paths and service-authorized image URLs whose
IDs match the assessed images. For reinspection, `prior_images` must contain validated `ImageInfo`
records for evidence retained from the prior result. Assembly derives dimensions from the local
images, counts and overall status from findings, and rejects dangling evidence or duplicate finding
IDs. It does not return local paths.

`render_html_report(inspection, image_paths) -> str` returns a self-contained HTML document with
escaped dynamic text and embedded Pillow evidence crops. `generate_html_report(inspection,
image_paths, output_path) -> Path` creates a file exclusively and refuses to overwrite an existing
path. The renderer currently uses the standard library and Pillow, not Jinja2. Step 7 above
explicitly requires Jinja2, and no Jinja2 dependency is installed or declared; this is a known
specification deviation requiring dependency/implementation approval before claiming strict Step 7
completion. The report should be opened locally in a browser for visual review when the environment
supports it; automated tests verify its structure and escaping, not browser rendering.

### Environment and commands

From the repository root, install the repository-declared development dependencies only in the
approved project environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m pytest backend/tests/test_engine_contract_adapter.py backend/tests/test_engine_reinspection.py backend/tests/test_engine_ratings.py backend/tests/test_engine_report.py -q
.\.venv\Scripts\python.exe -m pytest ml/tests -q
```

The ML drawing/OCR test dependency is declared in `ml/requirements-ocr.txt` and includes
`pdfplumber>=0.11,<1.0`; when approved for the environment, install with
`.\.venv\Scripts\python.exe -m pip install -r ml/requirements-ocr.txt`. The HTML specification
also calls for Jinja2, but it is not in the current requirements. Do not add either dependency
without the repository's required approval.

### Integration handoff

The integration service can consume the contract adapter or pass validated Pydantic models directly
to `run_inspection`. It should persist the returned findings and image flags; for reinspection, call
`run_reinspection` with persisted prior findings, then assemble a result with current and prior image
records before rendering. Keep original image paths server-side, authorize all URLs in the service,
and never accept arbitrary client paths. The service owns API response serialization and reviewer
events. The frontend should continue to use the schema field names and status values unchanged.

The following work is deliberately outside this module: API routes, request authorization,
application orchestration, database models/migrations/persistence, frontend rendering, and model
training. The current repository API does not call these module functions, so module-level tests do
not establish an application-level end-to-end workflow. Full ML suite execution also requires the
declared `pdfplumber` dependency; real-model validation requires representative trained models,
cabinet photographs/drawings, and reviewed expected outputs, none of which are included as safe
tracked fixtures.
