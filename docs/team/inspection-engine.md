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
