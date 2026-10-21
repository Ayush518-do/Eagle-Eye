# Dataset audit checklist

Use this document before selecting a dataset for training. A hosted dataset is not automatically certified, validated, or licensed for every use.

## Candidate dataset register

| Dataset | Intended task | Source/version | Images inspected | Target classes match? | Annotation quality | License checked? | Decision |
|---|---|---|---:|---|---|---|---|
| Electrical Devices | Physical component detection | Fill in | No | Pending | Pending | Pending | Pending |
| Breaker Detection | Supplementary component detection | Fill in | No | Pending | Pending | Pending | Pending |
| DELP / SkeySpot | Electrical drawing symbol detection | Fill in | No | Different domain; assess separately | Pending | Pending | Pending |
| MVTec AD | General industrial anomaly-detection research | Official version | No | Not cabinet-specific | Documented benchmark; verify version | Check restrictions | Optional/future |
| Team-collected matched cabinet set | End-to-end inspection evaluation | Record consent/source | Pending | Cabinet-specific | Reviewed labels required | Confirm permission | Essential |

Candidate links:
- https://universe.roboflow.com/vit-atwcp/electrical-devices
- https://universe.roboflow.com/circuit-breakers-detection/breaker-detection
- https://universe.roboflow.com/iitgn-motpy/delp
- https://www.mvtec.com/research-teaching/datasets/mvtec-ad

## Checklist per dataset

- [ ] Record exact source URL, version/date, download method and owner.
- [ ] Read the dataset license and usage restrictions.
- [ ] Inspect representative images and annotation overlays manually.
- [ ] Verify that class names have precise definitions and align with our taxonomy.
- [ ] Check annotation format and convert without losing labels.
- [ ] Look for corrupt files, missing annotations, bad boxes, wrong class names and duplicates.
- [ ] Group splits by cabinet/session/source where possible to reduce near-duplicate leakage.
- [ ] Keep a truly held-out test set that is not used for tuning.
- [ ] Record image counts by split and class.
- [ ] Evaluate separately on our own cabinet photographs.

## Important distinction between tasks

- Isolated component photos can help train object detection, but are not sufficient to validate full-cabinet comparison.
- Electrical plan symbols are not equivalent to physical cabinet components.
- General anomaly data does not directly teach missing-relay or wrong-rating detection.
- OCR/rating verification needs readable label examples and known expected specifications.
- Missing/extra/misplaced findings need matched reference/actual examples with reviewed ground truth.

## Evaluation to report

For detection: precision, recall, mAP and per-class results on held-out data.

For inspection: precision/recall of each discrepancy type, false missing-component rate, percentage sent to review, OCR exact-match accuracy on readable labels, and the outcome of reinspection. Document sample size and limitations; do not imply reliability from a small demo set.
