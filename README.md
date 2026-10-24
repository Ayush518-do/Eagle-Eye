# Eagle Eye — AI-Assisted Electrical Cabinet Inspection

Eagle Eye is a hackathon project for comparing an approved electrical cabinet reference layout with photographs of the real installation. It aims to highlight potential missing, extra, or misplaced components and check clearly visible component markings against approved specifications.

> **Safety boundary:** Eagle Eye is an inspection-assistance prototype, not an autonomous electrical safety certification system. Image-based inspection cannot verify hidden wiring or guarantee electrical safety. Uncertain and safety-critical findings require qualified human review.

## Problem

Manual cabinet inspection can be time-consuming and may overlook visible differences between an approved design and an installation. Eagle Eye aims to make inspection easier to review, document, and repeat.

## Planned workflow

1. Create or select a cabinet record.
2. Upload the approved reference layout and design revision.
3. Upload one or more photographs of the actual cabinet.
4. Detect supported components and read visible markings where possible.
5. Align reference and actual images when feasible.
6. Compare expected components with observed detections.
7. Present potential discrepancies with evidence and uncertainty flags.
8. Let an operator review findings, record corrective actions, and reinspect.
9. Save inspection evidence and history in a digital quality passport.

## Planned features

### Core inspection
- Component detection for a defined set of supported electrical component classes.
- Reference-versus-actual component and placement comparison.
- Ghost overlay to visualize expected layout against the actual photograph.
- Inspection findings with supporting image evidence.
- OCR for readable labels and ratings, compared with an approved specification.

### Reliability and traceability
- **Confidence gate:** flag blurry, obscured, low-confidence, or otherwise inconclusive observations for human review.
- **Multi-view verification:** support multiple photographs and associate close-ups with cabinet regions to reduce false missing-component findings.
- **Correction and reinspection:** preserve earlier findings and compare them against new evidence after corrective action.
- **Digital quality passport:** keep cabinet identity, design revision, photos, findings, reviewer decisions, corrective actions, and inspection history.

### Deferred roadmap
Advanced anomaly detection, manufacturing analytics, complete wire/terminal verification, automatic interpretation of arbitrary CAD formats, and automatic 3D reconstruction are deferred until the core inspection pipeline works and is evaluated.

## Proposed technology stack

| Area | Candidate technology | Purpose |
|---|---|---|
| Frontend | React + Vite | Dashboard, uploads, overlay, findings, review workflow |
| Backend | Python + FastAPI | API and inspection orchestration |
| Object detection | Ultralytics YOLO | Locate supported component classes |
| OCR | PaddleOCR | Read visible printed markings |
| Image processing | OpenCV | Alignment, cropping, overlay, image-quality checks |
| Inspection records | SQLite initially | Cabinets, design revisions, inspections and review events |
| Evidence files | Local folder initially | Uploaded and generated images |

This is a proposed implementation plan. Tools must be integrated and their performance tested before a feature is described as working.

## Repository layout

```text
frontend/           React + Vite UI
backend/            FastAPI API and inspection services
ml/                 Training, inference and evaluation scripts
data/               Dataset instructions; do not commit large/restricted datasets
tests/              Automated and inspection scenario tests
docs/               Architecture, API, dataset audit and roadmap
.github/workflows/  Basic continuous integration
```

## Dataset strategy

Public datasets will be assessed for relevance to the target cabinet, class definitions, annotation quality, train/validation/test separation, provenance, and license. Cabinet-specific matched reference/actual images and reviewed discrepancy labels are needed to evaluate the complete comparison workflow.

Candidate sources to audit (not certified or guaranteed suitable):
- [Electrical Devices — Roboflow Universe](https://universe.roboflow.com/vit-atwcp/electrical-devices)
- [Breaker Detection — Roboflow Universe](https://universe.roboflow.com/circuit-breakers-detection/breaker-detection)
- [DELP electrical layout plans — Roboflow Universe](https://universe.roboflow.com/iitgn-motpy/delp)
- [MVTec AD — official dataset page](https://www.mvtec.com/research-teaching/datasets/mvtec-ad)

Check the exact dataset version, labels, terms and license before use. See [`docs/dataset-audit.md`](docs/dataset-audit.md).

## Development priorities

1. Audit candidate datasets and run a pretrained detector.
2. Build the upload flow and a working end-to-end baseline.
3. Add component matching, alignment, ghost overlay, and evidence-backed findings.
4. Add confidence gating and multi-view support.
5. Add OCR/specification checks where image quality allows.
6. Add human review, correction/reinspection, and the digital quality passport.
7. Evaluate on cabinet examples not used for training.

See [`docs/roadmap.md`](docs/roadmap.md) and [`docs/architecture.md`](docs/architecture.md).

## Evaluation

Measure object detection with precision, recall, and mAP on a held-out test set. Separately evaluate inspection outcomes: missing/extra/misplaced component findings, rating discrepancies, inconclusive cases, and whether reinspection correctly updates prior findings. High object-detection mAP alone does not demonstrate reliable inspection.

## Project status

This repository is an initial scaffold. Features are planned until their implementation and evaluation are documented here.

## Team

Work is split into four parts with one branch each; see [`docs/team/README.md`](docs/team/README.md) and the hand-over formats in [`docs/contracts.md`](docs/contracts.md).

- Ayush
- Pranay
- Aditya
- Archita
