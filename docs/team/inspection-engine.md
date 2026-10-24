# Task 3: Inspection engine (rules, photo quality, reports)

**Branch:** `feature/inspection-engine` · **You own:** `backend/app/pipeline/`,
`backend/app/reports/`, `backend/tests/test_engine_*.py`, `config/thresholds.yaml`.
**Do not edit:** API routes or database code (Task 1), `frontend/` (Task 2), `ml/`.

## What you are building

The "brain" that turns *what the drawing expects* plus *what was seen in the photos* into findings.
It is plain Python with no database and no web code, which makes it easy to test with small examples.

```text
expected items (contract A) ─┐
observations   (contract B) ─┼─► run_inspection() ─► findings (contract C) + photo flags
photo files                 ─┘
```

Until the ML parts are ready, observations come from boxes people draw by hand (`source: "manual"`),
so everything here can be built and tested now.

## What already works

`backend/app/pipeline/compare.py` matches expected tags to read tags:

- tag read with high confidence → `verified`
- read with low confidence → `needs_review`
- not read anywhere → `inconclusive` (**never** "missing" from one photo)
- read but not in the drawing → `unexpected`, `needs_review`
- refuses `source: "synthetic"` data

Tests: `backend/tests/test_compare.py`.

## Step 1: The single entry point

Create `backend/app/pipeline/engine.py`:

```python
def run_inspection(expected_items, observations_by_image, image_paths, thresholds=None):
    """Returns (findings, image_flags). image_flags = {"IMG-001": ["low_sharpness"], ...}"""
    image_flags = {img: check_photo(path, thresholds) for img, path in image_paths.items()}
    findings = compare(expected_items, observations_by_image, thresholds)
    findings = apply_confidence_gate(findings, image_flags, thresholds)
    return findings, image_flags
```

Task 1 calls only this function. Keep the name and arguments stable, and tell Task 1 before you
change them.

## Step 2: Thresholds in one file

Put every number in `config/thresholds.yaml`, never scattered through the code:

```yaml
min_text_confidence: 0.80        # below this, an OCR reading needs review
min_detector_confidence: 0.50
min_photo_width: 1600            # pixels
min_sharpness: 100.0             # see Step 3
max_overexposed_fraction: 0.15   # share of nearly-white pixels
```

These are starting guesses. Write down which ones were tuned, and on what photos.

## Step 3: Photo-quality checks

`backend/app/pipeline/image_quality.py` (use OpenCV: `pip install opencv-python-headless`):

| Flag | How to measure | Meaning |
|---|---|---|
| `low_resolution` | width < `min_photo_width` | labels may be too small to read |
| `low_sharpness` | variance of the Laplacian < `min_sharpness` | the photo is probably blurry |
| `overexposed` | share of pixels with brightness > 250 > limit | glare may hide labels |

*Variance of the Laplacian* in plain words: the Laplacian highlights edges, so a sharp photo has
strong edges and a high variance, while a blurry one has a low variance.

```python
import cv2
gray = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
```

These are hints, not verdicts. Test with one sharp generated image and a blurred copy of it
(`cv2.GaussianBlur`); the blurred one must get the flag.

## Step 4: Confidence gate

`apply_confidence_gate()` lowers certainty, never raises it:

| Situation | Result |
|---|---|
| `verified`, but every photo showing it has `low_sharpness` | → `needs_review`, reason "photo may be blurry" |
| `potential_mismatch` read with confidence below threshold | → `needs_review` |
| Expected item has `rating.needs_review: true` | rating check skipped, reason says so |
| Two photos read different text for the same tag area | → `needs_review`, both readings in the reason |

Each rule gets its own test, with the input and expected output written out in the test.

## Step 5: Rating check

When a reading near a tag contains a rating, compare it with the drawing.
`backend/app/pipeline/ratings.py`:

```python
normalise_rating("10 A")  -> ("A", 10.0)
normalise_rating("10A")   -> ("A", 10.0)
normalise_rating("C10")   -> ("A", 10.0)   # breaker label: curve C, 10 amps
normalise_rating("24VDC") -> ("V", 24.0)
normalise_rating("CB11")  -> None          # a tag, not a rating
```

- Same unit and value → no extra finding.
- Different value → `rating_mismatch`, `potential_mismatch`, with expected and observed both shown.
- Can't parse → leave it alone. Never guess.

Which reading belongs to which tag: use the reading closest to the tag's box, within a limit set
in `thresholds.yaml`. Write tests with made-up coordinates.

## Step 6: Reinspection comparison

`compare_with_previous(old_findings, new_findings)`: a finding from the earlier inspection becomes
`resolved_after_reinspection` **only** if the new inspection has it `verified`. Anything else stays
open, and an old finding is never deleted.

## Step 7: Inspection report

`backend/app/reports/html_report.py` using Jinja2 (`pip install jinja2`) creates one HTML file per
inspection:

- cabinet, design revision, date, overall status
- findings table (same columns as the frontend)
- a small cropped image of each finding's evidence box (Pillow `Image.crop`)
- photo-quality flags in plain words
- footer: "Inspection assistance only. Uncertain findings require qualified human review."

Optional: a QR code (`pip install qrcode`) linking to the cabinet's history page.

Task 1 will expose it as `GET /api/inspections/{id}/report`.

## Tests

Name files `backend/tests/test_engine_*.py`. Only generated images and hand-written data, no
company photos. Cover every rule in Steps 3–6, including the "never call it missing" rule.

## Done when

- [ ] `run_inspection()` exists and Task 1 calls it.
- [ ] Every threshold is in `config/thresholds.yaml`.
- [ ] Blur, rating, gate and reinspection rules each have passing tests.
- [ ] An HTML report can be generated for a test inspection and opens in a browser.
- [ ] Add new packages to `backend/requirements.txt` (tell Task 1, who shares that file).

## Later, when ML is ready

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
