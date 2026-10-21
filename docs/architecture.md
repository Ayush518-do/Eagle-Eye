# Eagle Eye architecture

## Goal
Compare a known approved electrical-cabinet reference and component specification with one or more photographs of the real installation; show evidence-backed findings and retain the review history.

## Initial architecture

```text
React + Vite
    │ HTTP/JSON
    ▼
FastAPI backend
    ├── Image quality checks
    ├── Component detector (YOLO adapter)
    ├── OCR adapter (PaddleOCR)
    ├── Image alignment and overlay (OpenCV)
    ├── Reference/component matcher
    ├── Rule engine and confidence gate
    ├── Inspection/reinspection service
    └── Digital quality passport service
          ├── SQLite records
          └── Local evidence-image storage
```

Use one backend application with clear modules first; do not introduce microservices for the hackathon.

## Pipeline

1. Validate uploaded file type and size; create a cabinet and inspection record.
2. Associate the approved design revision and component specification.
3. Check photo adequacy (blur, resolution, glare/visibility heuristics). These checks are hints, not guarantees.
4. Detect supported components and optionally run OCR on component crops.
5. Align reference and actual image if the images and landmarks support alignment.
6. Match expected items to observations using explicit IDs/locations where available, then geometry and class as supporting evidence.
7. Return findings as `potential_mismatch`, `needs_review`, `inconclusive`, or reviewer-confirmed states. Never equate no detection in one view with proof of absence.
8. Save evidence, model/version metadata, reviewer decisions and links to prior/next inspections.

## Four required improvements

- **Confidence gate:** retain separate detector confidence, OCR confidence, image-quality flags and match quality. Calibrate thresholds against validation cases; no single score proves correctness.
- **Multi-view verification:** associate views with the cabinet and preferably a region/component. In the first version, allow manual association. Only fuse observations when association is sufficiently reliable.
- **Correction and reinspection:** create a new inspection linked to the previous one. Preserve the original finding and require new evidence or authorized review before marking resolved.
- **Digital quality passport:** retain cabinet ID, design revision, inspection timestamp, file references/hashes where practical, predictions, findings, reviewer decisions, corrective actions and inspection relationships.

## Non-goals for first version

Advanced anomaly detection, manufacturing analytics, complete wire/terminal verification, arbitrary-CAD parsing, hidden-wiring verification, or autonomous safety sign-off.

## Design principles

- Every finding should link to the image evidence and the reference revision used.
- Store observed text and expected specification separately.
- Unreadable/occluded should mean uncertain, not automatically incorrect.
- Keep inference replaceable behind a service interface so model changes do not require rewriting the UI.
- Be explicit about what was tested and what remains planned.
