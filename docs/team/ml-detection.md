# Part 1 — Vision / component detection (ML)

**Training steps: follow [`ml/detection/README.md`](../../ml/detection/README.md).** This file is the overview.

Branch: `feature/ml-detection` · Folder: `ml/detection/` · Produces: contract B (`kind: "component"`)

**Goal:** find where the parts are in a cabinet photo (draw a box around each breaker, power supply,
I/O baseplate…), so the backend knows which region each tag label belongs to.

## Constraints to know first

- There are no labels. A "label" here means a box drawn by a person around a part, with its class name.
  A detector cannot be trained or measured without them.
- Five photos, mostly one cabinet. Photo 5 is a different layout, so it is the only fair test image.
- Permission to train on company images is not yet confirmed. Do not train until it is.
- Licences: prefer Apache-2.0 models (D-FINE, YOLOX, RF-DETR). Ultralytics YOLO is AGPL-3.0; use only with team approval.

## Tasks

- [ ] 1. Agree the class list with Part 2 and Part 3 (start small: `mcb`, `power_supply`, `io_baseplate`, `tag_label`).
      Write it to `ml/detection/classes.yaml`.
- [ ] 2. `ml/detection/inspect_dataset.py`: report image count, size, duplicates, corrupt files, label counts per class.
- [ ] 3. Prepare the labelling set: working copies with location data (GPS) stripped, saved in `data/private/`.
      Optionally pre-fill `tag_label` boxes from Part 2's text detector, marked as machine proposals.
- [ ] 4. Label the photos in a local tool (for example CVAT or Label Studio running on your laptop — no cloud upload).
      Export COCO format. Record who labelled and who checked.
- [ ] 5. `ml/detection/split.py`: split by cabinet, never by single photo, so near-identical photos never sit on both sides.
- [ ] 6. Baseline: run a COCO-pretrained D-FINE-S or YOLOX-s on the photos unchanged and record the result.
      Expected outcome: it finds none of our classes. That is still a useful recorded baseline.
- [ ] 7. Implement `detect_components(image_path)` in `ml/interfaces.py` returning contract B.
      Raise `ModelUnavailableError` when no weights are configured (`DETECTOR_WEIGHTS_PATH` in `.env`).
- [ ] 8. Once permission is confirmed and labels are checked: fine-tune, with the config saved in `ml/detection/configs/`.
- [ ] 9. `ml/detection/evaluate.py`: precision, recall and mAP per class on the held-out image only.
      Refuse to run if the test image was in the training set.
- [ ] 10. `models/registry.json`: weights file name, SHA-256, dataset version, git commit, metrics. Weights stay out of Git.
- [ ] 11. Go/no-go note in `docs/`: is the detector good enough for the demo, and on what evidence.

## Done when

- `detect_components` works on an unseen photo and returns valid contract B.
- Every reported metric comes from `evaluate.py`, with the image count stated.
- A teammate can repeat the steps from `ml/detection/README.md`.

## Hand-over to Part 3

Until real weights exist, give Part 3 a small JSON file of observations drawn by hand
(`"source": "manual"`) so the comparison can be tested on real coordinates.
