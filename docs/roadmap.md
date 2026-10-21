# Development roadmap: 3 preparation days + 24-hour hackathon

The schedule is a target, not a guarantee. A stable end-to-end demo is more valuable than many unfinished features.

## Preparation day 1 — Dataset and AI baseline

- Audit Electrical Devices and Breaker Detection; choose one primary dataset and add the other only if it adds quality/relevant classes.
- Check exact licenses, image domain, label taxonomy, annotation format and duplicate risk.
- Set up Python environment and run a pretrained object detector on sample cabinet images.
- Define a small set of supported classes and a held-out real-cabinet evaluation set.
- Deliverable: documented dataset decision and detector baseline.

## Preparation day 2 — End-to-end app

- Create the React/Vite frontend and FastAPI backend.
- Connect a health endpoint and image upload.
- Show reference image, actual image, detections and a preliminary findings panel.
- Add OpenCV overlay with a controlled alignment path.
- Deliverable: working local flow, even if findings initially use sample/mock data while model integration is completed.

## Preparation day 3 — Reliability and records

- Add image-quality and uncertainty flags.
- Add multiple-view upload with manual view/component association.
- Add OCR + specification lookup only if time and image quality permit.
- Add SQLite records for cabinet, design revision, inspection, findings, review/correction and reinspection links.
- Test known normal, discrepancy and inconclusive examples; prepare backup demo files.
- Deliverable: stable prototype with documented feature status.

## Hackathon — 24 hours

- Hours 0–4: align to the exact prompt/judging criteria; freeze scope; get the current build running.
- Hours 4–10: fix model/data mismatch and improve reference matching/overlay.
- Hours 10–16: integrate confidence gate, multi-view, correction/reinspection and passport with highest-risk items first.
- Hours 16–20: end-to-end tests, false-positive checks, UI/report cleanup.
- Hours 20–24: freeze features, verify demo environment, rehearse pitch and keep a backup recording/screenshots.

## Priority order

1. Upload reference and actual photo.
2. Detect supported components.
3. Compare expected/observed components for a controlled example.
4. Ghost overlay and evidence-backed findings.
5. Confidence gate.
6. Multi-view upload/review.
7. Correction and reinspection.
8. Digital quality passport.
9. OCR/rating check, if feasible and demonstrable.

## Future only

Advanced anomaly detection, manufacturing analytics, complete wire/terminal verification, arbitrary CAD interpretation and automatic 3D reconstruction.
