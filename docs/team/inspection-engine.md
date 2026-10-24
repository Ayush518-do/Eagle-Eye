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
